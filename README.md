# TinyLB - Kubernetes LoadBalancer Bridge for Single-Node Environments

[![Go Report Card](https://goreportcard.com/badge/github.com/jctanner/tinylb)](https://goreportcard.com/report/github.com/jctanner/tinylb)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.11%2B-brightgreen.svg)](https://kubernetes.io/)

**TinyLB** is a minimal Kubernetes controller that enables Gateway API functionality on single-node environments (CRC, SNO, kind, minikube) by bridging LoadBalancer services to platform-specific external access mechanisms.

## 🎯 Problem Statement

Gateway API implementations like Istio create LoadBalancer services that cannot get external IPs in single-node development environments. This causes Gateways to remain in `PROGRAMMED: False` state, blocking Gateway API functionality.

**Before TinyLB:**
```bash
# LoadBalancer service stuck in pending state
kubectl get svc echo-gateway-istio
NAME                EXTERNAL-IP   PORT(S)
echo-gateway-istio  <pending>     80:32273/TCP

# Gateway cannot be programmed
kubectl get gateway echo-gateway
NAME           CLASS   ADDRESS   PROGRAMMED   AGE
echo-gateway   istio   (none)    False        5m
```

**After TinyLB:**
```bash
# LoadBalancer service gets external address
kubectl get svc echo-gateway-istio
NAME                EXTERNAL-IP                                    PORT(S)
echo-gateway-istio  echo-gateway-istio-echo-test.apps-crc.testing  80:32273/TCP

# Gateway becomes programmed and ready
kubectl get gateway echo-gateway
NAME           CLASS   ADDRESS                                        PROGRAMMED   AGE
echo-gateway   istio   echo-gateway-istio-echo-test.apps-crc.testing  True         5m
```

## 🚀 How It Works

TinyLB acts as a bridge between Kubernetes LoadBalancer services and platform-specific external access:

1. **Service Watcher**: Monitors LoadBalancer services with empty `status.loadBalancer.ingress`
2. **External Access Creator**: Creates platform-specific external access (OpenShift Routes, Ingress, etc.)
3. **Status Updater**: Updates LoadBalancer service status with external address
4. **Gateway Enabler**: Allows Gateway API controllers to complete configuration

## 🏗️ Architecture

```
Gateway API Controller → LoadBalancer Service → TinyLB → Platform External Access
        ↓                       ↓                ↓              ↓
   Creates Service         Stuck <pending>    Watches &     Route/Ingress
   Expects External IP                        Creates       Created
        ↓                                        ↓              ↓
   Waits for Address  ←────────────────────── Updates ←────── External Address
        ↓                                    Service Status    Available
   Gateway PROGRAMMED: True
```

## 📦 Installation

### Prerequisites
- Kubernetes 1.11.3+
- kubectl configured for your cluster
- Platform-specific requirements:
  - **OpenShift/CRC**: Routes API available
  - **Standard Kubernetes**: Ingress controller installed

### Quick Install

```bash
# Install TinyLB using kustomize directly from the repository
kubectl apply -k https://github.com/jctanner/tinylb/config/default

# Verify installation
kubectl get pods -n tinylb-system
NAME                               READY   STATUS    RESTARTS   AGE
tinylb-controller-manager-xxx      2/2     Running   0          1m
```

### Build and Install from Source

```bash
# Clone the repository
git clone https://github.com/jctanner/tinylb.git
cd tinylb

# Build and generate the installer manifest
make build-installer

# Install using the generated manifest
kubectl apply -f dist/install.yaml

# Verify installation
kubectl get pods -n tinylb-system
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/jctanner/tinylb.git
cd tinylb

# Install CRDs
make install

# Deploy controller with default image
make deploy

# Or deploy with custom image
make deploy IMG=your-registry/tinylb:latest
```

### Custom Image Installation

```bash
# Method 1: Using kustomize with image patch
kubectl apply -k https://github.com/jctanner/tinylb/config/default
kubectl patch deployment tinylb-controller-manager -n tinylb-system -p '{"spec":{"template":{"spec":{"containers":[{"name":"manager","image":"registry.tannerjc.net/odh/tinylb:latest"}]}}}}'

# Method 2: Using local kustomize with custom image
git clone https://github.com/jctanner/tinylb.git
cd tinylb
cd config/manager && kustomize edit set image controller=registry.tannerjc.net/odh/tinylb:latest
kustomize build config/default | kubectl apply -f -
```

### Uninstall

```bash
# If installed from source using make
make undeploy

# If installed using kustomize
kubectl delete -k https://github.com/jctanner/tinylb/config/default

# Remove CRDs (if installed separately)
make uninstall
```

## 🔧 Configuration

TinyLB is configured via environment variables in the deployment:

```yaml
env:
# Platform-specific settings
- name: PLATFORM
  value: "openshift"  # openshift, kubernetes, auto

# Hostname pattern for external access
- name: HOSTNAME_PATTERN
  value: "{service}-{namespace}.apps-crc.testing"

# Namespace filtering (empty = all namespaces)
- name: WATCH_NAMESPACES
  value: "default,echo-test"

# Logging configuration
- name: LOG_LEVEL
  value: "info"
```

### Hostname Pattern Configuration

TinyLB uses a configurable hostname pattern for external access. The default pattern is:
```
{service}-{namespace}.apps-crc.testing
```

**Available Variables:**
- `{service}`: Service name
- `{namespace}`: Service namespace  
- `{cluster}`: Cluster domain (if available)

**Examples:**
```yaml
# CRC/SNO environments
HOSTNAME_PATTERN: "{service}-{namespace}.apps-crc.testing"

# OpenShift AI/OpenDataHub
HOSTNAME_PATTERN: "{service}-{namespace}.apps.your-cluster.com"

# Custom domain
HOSTNAME_PATTERN: "{service}.{namespace}.tinylb.example.com"
```

## ⚙️ Controller Implementation Details

### Service Processing Logic

TinyLB processes services with the following criteria:

1. **Service Type Filtering**: Only `LoadBalancer` services are processed
2. **Status Checking**: Services with existing `status.loadBalancer.ingress` are skipped
3. **Port Selection**: Uses priority-based port selection algorithm
4. **Route Creation**: Creates OpenShift Routes with passthrough TLS termination
5. **Status Update**: Updates service status with external hostname

### Port Selection Algorithm

TinyLB uses a sophisticated port selection algorithm for optimal Gateway API compatibility:

```go
// Priority 1: Standard HTTPS ports (for passthrough mode)
// - 443, 8443

// Priority 2: Standard HTTP ports (fallback)  
// - 80, 8080

// Priority 3: Ports with "https" in the name
// - Any port with "https" substring

// Priority 4: Ports with "http" in the name
// - Any port with "http" substring

// Priority 5: Avoid known management/status ports
// - Skips: 15021, 15090, 9090, 8181 (Istio/Service Mesh)

// Fallback: First available port
```

This ensures Gateway API controllers receive the most appropriate port for external access.

### Route Configuration

For OpenShift environments, TinyLB creates Routes with the following configuration:

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: tinylb-{service-name}
  namespace: {service-namespace}
  labels:
    tinylb.io/managed: "true"
    tinylb.io/service: {service-name}
    tinylb.io/service-uid: {service-uid}
spec:
  host: {service-name}-{namespace}.apps-crc.testing
  to:
    kind: Service
    name: {service-name}
  port:
    targetPort: {selected-port}
  tls:
    termination: passthrough  # Preserves end-to-end TLS
```

**Key Features:**
- **Passthrough TLS**: Maintains end-to-end encryption for Service Mesh
- **Owner References**: Routes are automatically cleaned up when services are deleted
- **Label Management**: Enables service discovery and management
- **Port Mapping**: Uses intelligent port selection for optimal routing

### Reconciliation Flow

```go
1. Watch LoadBalancer services across all namespaces
2. Filter services without external IPs
3. Select optimal port using priority algorithm
4. Create/update OpenShift Route with:
   - Passthrough TLS termination
   - Calculated hostname
   - Owner references
   - Management labels
5. Update service status with route hostname
6. Log success and continue watching
```

## 🎯 Use Cases

### Service Mesh + Gateway API
Enable Istio Gateway API on single-node environments:

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: Gateway
metadata:
  name: my-gateway
spec:
  gatewayClassName: istio
  listeners:
  - name: default
    hostname: "*.apps-crc.testing"
    port: 80
    protocol: HTTP
```

### OpenShift AI / OpenDataHub Integration
Perfect for enabling Gateway API functionality in ODH environments:

```yaml
# Example ODH service configuration
apiVersion: v1
kind: Service
metadata:
  name: jupyter-gateway
  namespace: opendatahub
spec:
  type: LoadBalancer
  ports:
  - port: 443
    name: https
  selector:
    app: jupyter-gateway
```

TinyLB will automatically create:
- Route: `jupyter-gateway-opendatahub.apps-crc.testing`
- TLS: Passthrough termination
- Status: Updates service with external hostname

### Development Environments
- **CodeReady Containers (CRC)**: OpenShift development
- **kind**: Kubernetes in Docker
- **minikube**: Local Kubernetes development
- **Single Node OpenShift (SNO)**: Edge computing scenarios

### CI/CD Integration
Use TinyLB in automated testing pipelines requiring Gateway API functionality.

## 🔧 Manual Implementation (Without Controller)

If you prefer to implement the LoadBalancer bridge manually without the TinyLB controller, here's how to replicate the functionality:

### Step 1: Create a LoadBalancer Service

First, create your LoadBalancer service that will be stuck in `<pending>` state:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-gateway-service
  namespace: default
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8443
    name: https
  - port: 80
    targetPort: 8080
    name: http
  selector:
    app: my-gateway
```

```bash
kubectl apply -f service.yaml
# Service will show <pending> external IP
kubectl get svc my-gateway-service
```

### Step 2: Manually Create the OpenShift Route

Create a Route that follows TinyLB's pattern and logic:

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: tinylb-my-gateway-service
  namespace: default
  labels:
    tinylb.io/managed: "true"
    tinylb.io/service: my-gateway-service
    tinylb.io/service-uid: "REPLACE_WITH_SERVICE_UID"
  ownerReferences:
  - apiVersion: v1
    kind: Service
    name: my-gateway-service
    uid: "REPLACE_WITH_SERVICE_UID"
    controller: true
    blockOwnerDeletion: true
spec:
  host: my-gateway-service-default.apps-crc.testing
  to:
    kind: Service
    name: my-gateway-service
    weight: 100
  port:
    targetPort: 443  # TinyLB prioritizes HTTPS ports
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
```

To get the service UID for owner references:
```bash
SERVICE_UID=$(kubectl get service my-gateway-service -o jsonpath='{.metadata.uid}')
echo "Service UID: $SERVICE_UID"
```

### Step 3: Update Service Status with External Hostname

This is the tricky part - you need to patch the service status to include the route hostname. This requires proper RBAC permissions:

```bash
# Create a service account with appropriate permissions
kubectl create serviceaccount tinylb-manual
kubectl create clusterrole tinylb-manual --verb=get,list,watch,update,patch --resource=services,services/status
kubectl create clusterrolebinding tinylb-manual --clusterrole=tinylb-manual --serviceaccount=default:tinylb-manual

# Get the service account token
kubectl create token tinylb-manual --duration=1h
```

Then update the service status:

```bash
# Patch the service status to include the external hostname
kubectl patch service my-gateway-service --subresource=status --type=merge -p='{
  "status": {
    "loadBalancer": {
      "ingress": [
        {
          "hostname": "my-gateway-service-default.apps-crc.testing"
        }
      ]
    }
  }
}'
```

### Step 4: Verify the Manual Implementation

Check that everything is working:

```bash
# Service should now show external hostname
kubectl get svc my-gateway-service
# NAME                  TYPE           CLUSTER-IP       EXTERNAL-IP                                    PORT(S)
# my-gateway-service    LoadBalancer   172.30.123.45    my-gateway-service-default.apps-crc.testing   443:32001/TCP,80:32002/TCP

# Route should be accessible
kubectl get route tinylb-my-gateway-service
# NAME                        HOST/PORT                                      PATH   SERVICES             PORT   TERMINATION   WILDCARD
# tinylb-my-gateway-service   my-gateway-service-default.apps-crc.testing          my-gateway-service   443    passthrough   None

# Test external access
curl -k https://my-gateway-service-default.apps-crc.testing
```

### Port Selection Algorithm (Manual)

TinyLB uses this priority order when selecting ports. Apply the same logic manually:

1. **Priority 1**: Standard HTTPS ports (443, 8443)
2. **Priority 2**: Standard HTTP ports (80, 8080)  
3. **Priority 3**: Ports with "https" in the name
4. **Priority 4**: Ports with "http" in the name
5. **Priority 5**: Avoid management ports (15021, 15090, 9090, 8181)
6. **Fallback**: First available port

### Cleanup (Manual)

When removing the service, also clean up the route:

```bash
# The route should be auto-deleted due to owner references
kubectl delete service my-gateway-service
kubectl delete route tinylb-my-gateway-service  # Only if owner references didn't work
```

### Script-Based Manual Implementation

For automation, create a script that replicates TinyLB's behavior:

```bash
#!/bin/bash
# manual-tinylb.sh

SERVICE_NAME="$1"
NAMESPACE="$2"

if [ -z "$SERVICE_NAME" ] || [ -z "$NAMESPACE" ]; then
    echo "Usage: $0 <service-name> <namespace>"
    exit 1
fi

# Get service details
SERVICE_UID=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.metadata.uid}')
SERVICE_TYPE=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.spec.type}')

# Check if it's a LoadBalancer service
if [ "$SERVICE_TYPE" != "LoadBalancer" ]; then
    echo "Service $SERVICE_NAME is not a LoadBalancer service"
    exit 1
fi

# Check if it already has external IP
EXTERNAL_IP=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
if [ -n "$EXTERNAL_IP" ]; then
    echo "Service $SERVICE_NAME already has external IP: $EXTERNAL_IP"
    exit 0
fi

# Create the route
ROUTE_NAME="tinylb-$SERVICE_NAME"
HOSTNAME="$SERVICE_NAME-$NAMESPACE.apps-crc.testing"

kubectl apply -f - <<EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: $ROUTE_NAME
  namespace: $NAMESPACE
  labels:
    tinylb.io/managed: "true"
    tinylb.io/service: $SERVICE_NAME
    tinylb.io/service-uid: $SERVICE_UID
  ownerReferences:
  - apiVersion: v1
    kind: Service
    name: $SERVICE_NAME
    uid: $SERVICE_UID
    controller: true
    blockOwnerDeletion: true
spec:
  host: $HOSTNAME
  to:
    kind: Service
    name: $SERVICE_NAME
    weight: 100
  port:
    targetPort: 443
  tls:
    termination: passthrough
    insecureEdgeTerminationPolicy: Redirect
EOF

# Update service status
kubectl patch service $SERVICE_NAME -n $NAMESPACE --subresource=status --type=merge -p="{
  \"status\": {
    \"loadBalancer\": {
      \"ingress\": [
        {
          \"hostname\": \"$HOSTNAME\"
        }
      ]
    }
  }
}"

echo "Successfully created route and updated service status for $SERVICE_NAME"
echo "External hostname: $HOSTNAME"
```

### Manual vs Controller Benefits

| Aspect | Manual Implementation | TinyLB Controller |
|--------|----------------------|-------------------|
| **Setup** | One-time per service | Automatic for all services |
| **Maintenance** | Manual updates required | Self-healing and automatic |
| **Port Selection** | Manual decision | Intelligent algorithm |
| **Cleanup** | Manual (unless owner refs work) | Automatic via owner references |
| **Monitoring** | No built-in monitoring | Prometheus metrics |
| **Error Handling** | Manual intervention | Automatic retry logic |
| **Scalability** | Labor intensive | Handles many services |

The manual approach is useful for:
- **Understanding** how TinyLB works internally
- **Debugging** TinyLB behavior
- **One-off** services in environments where installing TinyLB isn't feasible
- **Custom** routing requirements that differ from TinyLB's algorithm

## 🔒 Security Features

### TLS/mTLS Support
TinyLB works seamlessly with Service Mesh security:

```yaml
# Automatic TLS termination via OpenShift Routes
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: tinylb-my-service
spec:
  host: my-service-default.apps-crc.testing
  tls:
    termination: passthrough  # Preserves Service Mesh mTLS
    insecureEdgeTerminationPolicy: Redirect
```

**Security Benefits:**
- **End-to-End TLS**: Passthrough termination preserves Service Mesh encryption
- **Certificate Management**: Leverages existing Service Mesh certificates
- **mTLS Compatibility**: Works with Istio PeerAuthentication policies
- **Automatic Redirect**: HTTP traffic redirected to HTTPS

### RBAC
TinyLB requires minimal RBAC permissions:
- `services`: get, list, watch, update
- `routes.route.openshift.io`: get, list, watch, create, update, delete
- `ingresses.networking.k8s.io`: get, list, watch, create, update, delete

## 📊 Monitoring

TinyLB exposes Prometheus metrics:

```
# Service processing metrics
tinylb_services_processed_total{platform="openshift"} 5
tinylb_services_current{platform="openshift"} 3

# Error metrics
tinylb_errors_total{type="route_creation"} 0
tinylb_errors_total{type="status_update"} 0
```

## 🔍 Troubleshooting

### Common Issues

**Gateway remains `PROGRAMMED: False`**
```bash
# Check TinyLB logs
kubectl logs -n tinylb-system deployment/tinylb-controller-manager

# Verify service status
kubectl get svc -A | grep LoadBalancer
```

**Route/Ingress not created**
```bash
# Check RBAC permissions
kubectl auth can-i create routes.route.openshift.io --as=system:serviceaccount:tinylb-system:tinylb-controller-manager

# Verify TinyLB configuration
kubectl get configmap tinylb-config -n tinylb-system -o yaml
```

**Port selection issues**
```bash
# Check service ports
kubectl get svc my-service -o yaml

# Verify route port mapping
kubectl get route tinylb-my-service -o yaml
```

### Debug Mode
Enable debug logging:
```bash
kubectl patch deployment tinylb-controller-manager -n tinylb-system -p '{"spec":{"template":{"spec":{"containers":[{"name":"manager","env":[{"name":"LOG_LEVEL","value":"debug"}]}]}}}}'
```

## 🛠️ Development

### Building from Source
```bash
# Clone repository
git clone https://github.com/jctanner/tinylb.git
cd tinylb

# Build binary
make build

# Build container image
make docker-build IMG=registry.tannerjc.net/odh/tinylb:latest
```

### Testing
```bash
# Run unit tests
make test

# Run integration tests
make test-integration

# Run e2e tests (requires cluster)
make test-e2e
```

### Local Development
```bash
# Run controller locally
make run

# Deploy to cluster
make deploy IMG=registry.tannerjc.net/odh/tinylb:latest
```

### Development Workflow

**Important**: The `make deploy` and `make build-installer` targets do NOT build or push Docker images. They assume the image already exists in the registry.

#### Local Development (Recommended)

For local development, use `make run` which runs the controller directly on your host machine:

```bash
# Run controller locally (best for development)
make run
```

**How it works:**
- Runs the controller binary directly on your machine using `go run ./cmd/main.go`
- Connects to your Kubernetes cluster via `~/.kube/config`
- No Docker image building, pushing, or deployment required
- Fastest iteration cycle for development and testing
- Controller logs appear directly in your terminal

**No CRDs Required:**
- TinyLB doesn't define custom resources, so `make install` is not needed
- Works with existing Kubernetes `Service` resources and OpenShift `Route` resources
- You can run `make run` immediately after cloning the repository

**Prerequisites:**
- Go 1.24+ installed
- kubectl configured to connect to your cluster
- Cluster must have OpenShift Route API (for OpenShift/CRC) or Ingress API

#### Complete Development Workflow
```bash
# 1. Build the Docker image
make docker-build

# 2. Push to registry (required for deployment)
make docker-push

# 3. Deploy to cluster
make deploy
```

#### Generate Installation Manifest
```bash
# Build and push image first
make docker-build docker-push

# Generate dist/install.yaml
make build-installer

# Apply the generated manifest
kubectl apply -f dist/install.yaml
```

#### Custom Registry Workflow
```bash
# Build and push to custom registry
make docker-build docker-push IMG=your-registry/tinylb:your-tag

# Deploy with custom image
make deploy IMG=your-registry/tinylb:your-tag

# Or generate installer with custom image
make build-installer IMG=your-registry/tinylb:your-tag
```

**Note**: If you skip the `make docker-push` step, Kubernetes will fail to pull the image and pods will be in `ImagePullBackOff` state.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Process
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Run tests (`make test`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Code of Conduct
This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## 📋 Roadmap

- [ ] **Multi-platform Support**: Kubernetes Ingress, AWS ALB, GCP Load Balancer
- [ ] **Advanced Routing**: Path-based routing, weighted traffic splitting
- [ ] **Observability**: Enhanced metrics, tracing, health checks
- [ ] **Security**: Certificate management, policy enforcement
- [ ] **Performance**: Optimized reconciliation, caching

## 🎉 Success Stories

TinyLB has enabled Gateway API functionality in:
- **Red Hat OpenShift Service Mesh 3.0** on CRC environments
- **Istio Gateway API** deployments on kind clusters
- **OpenShift AI/OpenDataHub** development environments
- **CI/CD pipelines** requiring Gateway API testing
- **Edge computing** scenarios with Single Node OpenShift

## 📚 Documentation

- [Installation Guide](docs/installation.md)
- [Configuration Reference](docs/configuration.md)
- [Platform Support](docs/platforms.md)
- [Security Guide](docs/security.md)
- [API Reference](docs/api.md)

## 🔗 Related Projects

- [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/)
- [Istio](https://istio.io/)
- [OpenShift Service Mesh](https://docs.openshift.com/container-platform/latest/service_mesh/v2x/ossm-about.html)
- [OpenShift Routes](https://docs.openshift.com/container-platform/latest/networking/routes/route-configuration.html)
- [OpenShift AI](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed)
- [OpenDataHub](https://opendatahub.io/)

## 📄 License

Copyright 2025 TinyLB Contributors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## 🙏 Acknowledgments

- **kubebuilder** for the excellent controller framework
- **OpenShift** for the Route API inspiration
- **Istio** for Gateway API leadership
- **Kubernetes SIG-Network** for the Gateway API specification
- **Red Hat** for OpenShift AI and OpenDataHub innovation

---

⭐ **Star this project** if TinyLB helped enable Gateway API in your environment!

🐛 **Found a bug?** [Open an issue](https://github.com/jctanner/tinylb/issues/new/choose)

💡 **Have an idea?** [Start a discussion](https://github.com/jctanner/tinylb/discussions)

