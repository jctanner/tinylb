/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import (
	"context"
	"fmt"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	routev1 "github.com/openshift/api/route/v1"
)

// ServiceReconciler reconciles a Service object
type ServiceReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// selectHTTPPort selects the best port for HTTP/HTTPS traffic from a service's ports
// Since we use passthrough TLS termination, we prioritize HTTPS ports
func selectHTTPPort(ports []corev1.ServicePort) *corev1.ServicePort {
	// Priority 1: Standard HTTPS ports (for passthrough mode)
	for _, port := range ports {
		if port.Port == 443 || port.Port == 8443 {
			return &port
		}
	}

	// Priority 2: Standard HTTP ports (fallback)
	for _, port := range ports {
		if port.Port == 80 || port.Port == 8080 {
			return &port
		}
	}

	// Priority 3: Ports with "https" in the name
	for _, port := range ports {
		if strings.Contains(strings.ToLower(port.Name), "https") {
			return &port
		}
	}

	// Priority 4: Ports with "http" in the name
	for _, port := range ports {
		if strings.Contains(strings.ToLower(port.Name), "http") {
			return &port
		}
	}

	// Priority 5: Avoid known management/status ports
	for _, port := range ports {
		// Skip common management ports
		if port.Port == 15021 || port.Port == 15090 || port.Port == 9090 || port.Port == 8181 {
			continue
		}
		return &port
	}

	// Fallback: return first port if nothing else matches
	if len(ports) > 0 {
		return &ports[0]
	}

	return nil
}

// +kubebuilder:rbac:groups=core,resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=core,resources=services/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=core,resources=services/finalizers,verbs=update
// +kubebuilder:rbac:groups=route.openshift.io,resources=routes,verbs=get;list;watch;create;update;patch;delete

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
func (r *ServiceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Get the service
	var service corev1.Service
	if err := r.Get(ctx, req.NamespacedName, &service); err != nil {
		if errors.IsNotFound(err) {
			// Service was deleted, cleanup will be handled by owner references
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Unable to fetch Service")
		return ctrl.Result{}, err
	}

	// Only process LoadBalancer services
	if service.Spec.Type != corev1.ServiceTypeLoadBalancer {
		return ctrl.Result{}, nil
	}

	// Check if service already has an external IP
	if len(service.Status.LoadBalancer.Ingress) > 0 {
		// Service already has an external IP, nothing to do
		return ctrl.Result{}, nil
	}

	logger.Info("Processing LoadBalancer service without external IP", "service", service.Name)

	// Create or update the OpenShift Route
	route := &routev1.Route{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("tinylb-%s", service.Name),
			Namespace: service.Namespace,
			Labels: map[string]string{
				"tinylb.io/managed":     "true",
				"tinylb.io/service":     service.Name,
				"tinylb.io/service-uid": string(service.UID),
			},
		},
		Spec: routev1.RouteSpec{
			Host: fmt.Sprintf("%s-%s.apps-crc.testing", service.Name, service.Namespace),
			To: routev1.RouteTargetReference{
				Kind: "Service",
				Name: service.Name,
			},
			TLS: &routev1.TLSConfig{
				Termination: routev1.TLSTerminationPassthrough,
			},
		},
	}

	// Set the service port if specified
	if len(service.Spec.Ports) > 0 {
		// Select the best HTTP port for the route
		port := selectHTTPPort(service.Spec.Ports)
		if port != nil {
			route.Spec.Port = &routev1.RoutePort{
				TargetPort: intstr.FromInt(int(port.Port)),
			}
			logger.Info("Selected port for Route", "service", service.Name, "port", port.Port, "portName", port.Name)
		}
	}

	// Set owner reference so route is cleaned up when service is deleted
	if err := controllerutil.SetOwnerReference(&service, route, r.Scheme); err != nil {
		logger.Error(err, "Unable to set owner reference on Route")
		return ctrl.Result{}, err
	}

	// Create or update the route
	if err := r.Get(ctx, types.NamespacedName{Name: route.Name, Namespace: route.Namespace}, &routev1.Route{}); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("Creating Route for LoadBalancer service", "route", route.Name, "service", service.Name)
			if err := r.Create(ctx, route); err != nil {
				logger.Error(err, "Unable to create Route")
				return ctrl.Result{}, err
			}
		} else {
			logger.Error(err, "Unable to get Route")
			return ctrl.Result{}, err
		}
	}

	// Update service status with the route hostname
	serviceCopy := service.DeepCopy()
	serviceCopy.Status.LoadBalancer.Ingress = []corev1.LoadBalancerIngress{
		{
			Hostname: route.Spec.Host,
		},
	}

	if err := r.Status().Update(ctx, serviceCopy); err != nil {
		logger.Error(err, "Unable to update Service status")
		return ctrl.Result{RequeueAfter: time.Second * 10}, err
	}

	logger.Info("Successfully created Route and updated Service status",
		"service", service.Name,
		"route", route.Name,
		"hostname", route.Spec.Host)

	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *ServiceReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&corev1.Service{}).
		Owns(&routev1.Route{}).
		Named("service").
		Complete(r)
}
