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
	"slices"
	"time"

	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	routev1 "github.com/openshift/api/route/v1"
	corev1 "k8s.io/api/core/v1"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"
)

// GatewayReconciler reconciles a Gateway object
type GatewayReconciler struct {
	client.Client
	Scheme *runtime.Scheme

	// Configuration
	SupportedGatewayClasses []string // e.g., ["istio"]
	RouteNamespace          string   // OpenShift route namespace (empty = same as gateway)
}

// getLoadBalancerServiceName determines the expected LoadBalancer service name for a Gateway
// Based on current TinyLB behavior, this follows patterns like: {gateway-name}-{gatewayClassName}
func (r *GatewayReconciler) getLoadBalancerServiceName(gateway *gatewayv1.Gateway) string {
	gatewayClassName := string(gateway.Spec.GatewayClassName)
	return fmt.Sprintf("%s-%s", gateway.Name, gatewayClassName)
}

// isGatewayClassSupported checks if the gateway class is supported by TinyLB
func (r *GatewayReconciler) isGatewayClassSupported(gatewayClassName string) bool {
	return slices.Contains(r.SupportedGatewayClasses, gatewayClassName)
}

// updateGatewayCondition updates or adds a condition to the Gateway status
func (r *GatewayReconciler) updateGatewayCondition(ctx context.Context, gateway *gatewayv1.Gateway, conditionType gatewayv1.GatewayConditionType, status metav1.ConditionStatus, reason gatewayv1.GatewayConditionReason, message string) error {
	condition := metav1.Condition{
		Type:               string(conditionType),
		Status:             status,
		Reason:             string(reason),
		Message:            message,
		LastTransitionTime: metav1.Now(),
	}

	meta.SetStatusCondition(&gateway.Status.Conditions, condition)
	return r.Status().Update(ctx, gateway)
}

// updateGatewayAddresses updates the Gateway status addresses
func (r *GatewayReconciler) updateGatewayAddresses(ctx context.Context, gateway *gatewayv1.Gateway, hostname string) error {
	// Only update addresses if there's a hostname
	if hostname != "" {
		addressType := gatewayv1.HostnameAddressType
		gateway.Status.Addresses = []gatewayv1.GatewayStatusAddress{
			{
				Type:  &addressType,
				Value: hostname,
			},
		}
	} else {
		gateway.Status.Addresses = []gatewayv1.GatewayStatusAddress{}
	}
	return r.Status().Update(ctx, gateway)
}

// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways,verbs=get;list;watch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=core,resources=services,verbs=get;list;watch
// +kubebuilder:rbac:groups=route.openshift.io,resources=routes,verbs=get;list;watch

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
func (r *GatewayReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Get the Gateway
	var gateway gatewayv1.Gateway
	if err := r.Get(ctx, req.NamespacedName, &gateway); err != nil {
		if errors.IsNotFound(err) {
			// Gateway was deleted, nothing to do
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Unable to fetch Gateway")
		return ctrl.Result{}, err
	}

	logger.Info("Processing Gateway", "gateway", gateway.Name, "gatewayClassName", gateway.Spec.GatewayClassName)

	// Check if this is a supported Gateway class
	gatewayClassName := string(gateway.Spec.GatewayClassName)
	if !r.isGatewayClassSupported(gatewayClassName) {
		logger.Info("Gateway class not supported, skipping", "gatewayClassName", gatewayClassName)
		return ctrl.Result{}, nil
	}

	// Always mark supported Gateway classes as Accepted
	if err := r.updateGatewayCondition(ctx, &gateway, gatewayv1.GatewayConditionAccepted, metav1.ConditionTrue, gatewayv1.GatewayReasonAccepted, "Gateway is accepted"); err != nil {
		logger.Error(err, "Unable to update Gateway Accepted condition")
		return ctrl.Result{RequeueAfter: time.Second * 10}, err
	}

	// Find the expected LoadBalancer service name
	serviceName := r.getLoadBalancerServiceName(&gateway)
	logger.Info("Looking for LoadBalancer service", "service", serviceName)

	// Get the LoadBalancer service
	serviceNamespace := gateway.Namespace
	var service corev1.Service
	if err := r.Get(ctx, types.NamespacedName{Name: serviceName, Namespace: serviceNamespace}, &service); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("LoadBalancer service not found, Gateway not programmed", "service", serviceName)
			// Service doesn't exist, Gateway is not programmed
			if err := r.updateGatewayCondition(ctx, &gateway, gatewayv1.GatewayConditionProgrammed, metav1.ConditionFalse, gatewayv1.GatewayReasonNoResources, fmt.Sprintf("LoadBalancer service %s not found", serviceName)); err != nil {
				logger.Error(err, "Unable to update Gateway Programmed condition")
				return ctrl.Result{RequeueAfter: time.Second * 10}, err
			}
			// Clear addresses
			if err := r.updateGatewayAddresses(ctx, &gateway, ""); err != nil {
				logger.Error(err, "Unable to clear Gateway addresses")
				return ctrl.Result{RequeueAfter: time.Second * 10}, err
			}
			return ctrl.Result{RequeueAfter: time.Second * 30}, nil
		}
		logger.Error(err, "Unable to fetch LoadBalancer service")
		return ctrl.Result{}, err
	}

	// Check if service is LoadBalancer type
	if service.Spec.Type != corev1.ServiceTypeLoadBalancer {
		logger.Info("Service is not LoadBalancer type, Gateway not programmed", "service", serviceName, "type", service.Spec.Type)
		if err := r.updateGatewayCondition(ctx, &gateway, gatewayv1.GatewayConditionProgrammed, metav1.ConditionFalse, gatewayv1.GatewayReasonNoResources, fmt.Sprintf("Service %s is not LoadBalancer type", serviceName)); err != nil {
			logger.Error(err, "Unable to update Gateway Programmed condition")
			return ctrl.Result{RequeueAfter: time.Second * 10}, err
		}
		// Clear addresses
		if err := r.updateGatewayAddresses(ctx, &gateway, ""); err != nil {
			logger.Error(err, "Unable to clear Gateway addresses")
			return ctrl.Result{RequeueAfter: time.Second * 10}, err
		}
		return ctrl.Result{}, nil
	}

	// Check if service has external IP/hostname (indicating TinyLB processed it)
	if len(service.Status.LoadBalancer.Ingress) == 0 {
		logger.Info("LoadBalancer service has no external IP, Gateway not programmed yet", "service", serviceName)
		if err := r.updateGatewayCondition(ctx, &gateway, gatewayv1.GatewayConditionProgrammed, metav1.ConditionFalse, gatewayv1.GatewayReasonPending, fmt.Sprintf("LoadBalancer service %s has no external IP", serviceName)); err != nil {
			logger.Error(err, "Unable to update Gateway Programmed condition")
			return ctrl.Result{RequeueAfter: time.Second * 10}, err
		}
		// Clear addresses
		if err := r.updateGatewayAddresses(ctx, &gateway, ""); err != nil {
			logger.Error(err, "Unable to clear Gateway addresses")
			return ctrl.Result{RequeueAfter: time.Second * 10}, err
		}
		return ctrl.Result{RequeueAfter: time.Second * 30}, nil
	}

	// Service has external IP, check if Route exists
	routeName := fmt.Sprintf("tinylb-%s", serviceName)
	routeNamespace := serviceNamespace
	if r.RouteNamespace != "" {
		routeNamespace = r.RouteNamespace
	}

	var route routev1.Route
	if err := r.Get(ctx, types.NamespacedName{Name: routeName, Namespace: routeNamespace}, &route); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("Route not found, Gateway not programmed", "route", routeName)
			if err := r.updateGatewayCondition(ctx, &gateway, gatewayv1.GatewayConditionProgrammed, metav1.ConditionFalse, gatewayv1.GatewayReasonNoResources, fmt.Sprintf("Route %s not found", routeName)); err != nil {
				logger.Error(err, "Unable to update Gateway Programmed condition")
				return ctrl.Result{RequeueAfter: time.Second * 10}, err
			}
			// Clear addresses
			if err := r.updateGatewayAddresses(ctx, &gateway, ""); err != nil {
				logger.Error(err, "Unable to clear Gateway addresses")
				return ctrl.Result{RequeueAfter: time.Second * 10}, err
			}
			return ctrl.Result{RequeueAfter: time.Second * 30}, nil
		}
		logger.Error(err, "Unable to fetch Route")
		return ctrl.Result{}, err
	}

	// Route exists, Gateway is programmed
	hostname := service.Status.LoadBalancer.Ingress[0].Hostname
	if hostname == "" && service.Status.LoadBalancer.Ingress[0].IP != "" {
		hostname = service.Status.LoadBalancer.Ingress[0].IP
	}

	// Prefer Route hostname if available
	if route.Spec.Host != "" {
		hostname = route.Spec.Host
	}

	logger.Info("Gateway is programmed", "service", serviceName, "route", routeName, "hostname", hostname)

	// Update Gateway as programmed
	if err := r.updateGatewayCondition(ctx, &gateway, gatewayv1.GatewayConditionProgrammed, metav1.ConditionTrue, gatewayv1.GatewayReasonProgrammed, "Gateway is programmed"); err != nil {
		logger.Error(err, "Unable to update Gateway Programmed condition")
		return ctrl.Result{RequeueAfter: time.Second * 10}, err
	}

	// Update Gateway addresses
	if err := r.updateGatewayAddresses(ctx, &gateway, hostname); err != nil {
		logger.Error(err, "Unable to update Gateway addresses")
		return ctrl.Result{RequeueAfter: time.Second * 10}, err
	}

	logger.Info("Successfully updated Gateway status", "gateway", gateway.Name, "hostname", hostname)

	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *GatewayReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&gatewayv1.Gateway{}).
		Named("gateway").
		Complete(r)
}
