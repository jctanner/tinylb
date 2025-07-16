# TinyLB Technical Context

## Project Overview

TinyLB is a Kubernetes controller that enables Gateway API functionality in single-node development environments by bridging LoadBalancer services to platform-specific external access mechanisms.

**Primary Function**: Watches LoadBalancer services without external IPs and creates OpenShift Routes to provide external access, then updates the service status with the external hostname.

**Target Environments**: CodeReady Containers (CRC), Single Node OpenShift (SNO), kind, minikube, and other single-node Kubernetes environments.

## Architecture

### Core Components

**Main Controller** (`cmd/main.go`):
- Standard kubebuilder controller manager setup
- Configures metrics endpoint on :8443 (HTTPS) or :8080 (HTTP)
- Health probe endpoint on :8081
- Supports leader election for HA deployments
- TLS certificate management for webhook and metrics

**Service Controller** (`internal/controller/service_controller.go`):
- Reconciles `core/v1/Service` resources
- Watches services of type `LoadBalancer`
- Creates and manages `route.openshift.io/v1/Route` resources
- Updates service status with external hostname

### Controller Logic Flow

1. **Service Filtering**: Only processes services with `spec.type: LoadBalancer`
2. **Status Check**: Skips services that already have `status.loadBalancer.ingress`
3. **Port Selection**: Uses priority algorithm to select optimal port
4. **Route Creation**: Creates OpenShift Route with passthrough TLS
5. **Status Update**: Updates service status with route hostname
6. **Owner References**: Links route to service for automatic cleanup

### Port Selection Algorithm

Priority order for selecting service ports:
1. Standard HTTPS ports: 443, 8443
2. Standard HTTP ports: 80, 8080
3. Ports with "https" in name (case-insensitive)
4. Ports with "http" in name (case-insensitive)
5. Any port except management ports (15021, 15090, 9090, 8181)
6. Fallback to first available port

## Key Implementation Details

### Route Configuration

Created routes have these specifications:
- **Name**: `tinylb-{service-name}`
- **Hostname**: `{service-name}-{namespace}.apps-crc.testing`
- **TLS Termination**: Passthrough (preserves end-to-end encryption)
- **Target**: References the original service
- **Port**: Selected using priority algorithm
- **Labels**: `tinylb.io/managed: "true"`, `tinylb.io/service: {service-name}`, `tinylb.io/service-uid: {service-uid}`

### RBAC Requirements

Controller requires these permissions:
- `services`: get, list, watch, update, patch (for status updates)
- `services/status`: get, update, patch
- `routes.route.openshift.io`: get, list, watch, create, update, patch, delete

### Service Status Update

Updates `status.loadBalancer.ingress` with:
```yaml
status:
  loadBalancer:
    ingress:
    - hostname: {service-name}-{namespace}.apps-crc.testing
```

## Project Structure

```
tinylb/
├── cmd/main.go                           # Controller manager entry point
├── internal/controller/
│   ├── service_controller.go             # Core reconciliation logic
│   ├── service_controller_test.go        # Unit tests (minimal)
│   └── suite_test.go                     # Test suite setup
├── config/                               # Kubernetes manifests
│   ├── default/                          # Default kustomization
│   ├── manager/                          # Manager deployment
│   ├── rbac/                            # RBAC configuration
│   ├── network-policy/                   # Network policies
│   └── prometheus/                       # Monitoring configuration
├── test/
│   ├── e2e/                             # End-to-end tests
│   └── utils/                           # Test utilities
├── Dockerfile                           # Container build
├── Makefile                             # Build and deployment targets
└── PROJECT                              # Kubebuilder project config
```

## Dependencies

### Core Dependencies
- `sigs.k8s.io/controller-runtime v0.21.0` - Controller framework
- `k8s.io/client-go v0.33.0` - Kubernetes client library
- `k8s.io/api v0.33.0` - Kubernetes API types
- `github.com/openshift/api` - OpenShift API types (Routes)

### Testing Dependencies
- `github.com/onsi/ginkgo/v2 v2.22.0` - BDD testing framework
- `github.com/onsi/gomega v1.36.1` - Matcher library for Ginkgo

### Build Tools
- Go 1.24.0 - Programming language
- kubebuilder v4.6.0 - Controller scaffolding tool
- controller-gen v0.18.0 - Code generation
- kustomize v5.6.0 - Configuration management

## Build and Deployment

### Local Development
```bash
make run                    # Run controller locally
make test                   # Run unit tests
make test-e2e              # Run e2e tests with Kind
```

### Container Build
```bash
make docker-build IMG=registry.example.com/tinylb:latest
make docker-push IMG=registry.example.com/tinylb:latest
```

### Deployment
```bash
make deploy IMG=registry.example.com/tinylb:latest
make undeploy              # Remove from cluster
```

### Installation Manifest
```bash
make build-installer       # Generates dist/install.yaml
```

## Testing Strategy

### Unit Tests
- Located in `internal/controller/service_controller_test.go`
- Currently minimal, uses Ginkgo/Gomega framework
- Tests controller reconciliation logic

### E2E Tests
- Located in `test/e2e/e2e_test.go`
- Uses Kind for isolated testing environment
- Tests controller deployment and metrics endpoint
- Validates RBAC and service account configuration

### Test Environment
- Kind cluster named `tinylb-test-e2e`
- Namespace: `tinylb-system`
- Service account: `tinylb-controller-manager`
- Metrics service: `tinylb-controller-manager-metrics-service`

## Configuration

### Environment Variables
Controller supports configuration via environment variables:
- `PLATFORM`: Target platform (openshift, kubernetes, auto)
- `HOSTNAME_PATTERN`: Hostname pattern for external access
- `WATCH_NAMESPACES`: Comma-separated list of namespaces to watch
- `LOG_LEVEL`: Logging level (info, debug, error)

### Default Configuration
- Metrics endpoint: :8443 (HTTPS with authentication)
- Health probe: :8081
- Leader election: Disabled by default
- Hostname pattern: `{service}-{namespace}.apps-crc.testing`

## Problem Context

### Gateway API Challenge
Gateway API implementations create LoadBalancer services that cannot receive external IPs in single-node environments. This prevents Gateway resources from transitioning to `PROGRAMMED: True` state.

### Service Mesh Integration
Works with Istio and OpenShift Service Mesh by:
- Using passthrough TLS termination
- Preserving end-to-end encryption
- Supporting mTLS scenarios
- Maintaining certificate chain integrity

### Development Environment Support
Enables Gateway API functionality in environments where traditional LoadBalancer implementations are unavailable or impractical.

## Security Considerations

- Minimal RBAC permissions required
- TLS termination set to passthrough (no certificate handling)
- Service account token-based authentication for metrics
- Restricted pod security policies supported
- No sensitive data storage or processing

## Monitoring and Observability

### Metrics
- Prometheus metrics endpoint at :8443/metrics
- Controller runtime metrics included
- Custom metrics for service processing (planned)

### Health Checks
- Liveness probe: /healthz
- Readiness probe: /readyz
- Both available on :8081

### Logging
- Structured logging using controller-runtime/log
- Configurable log levels
- Request tracing for reconciliation events 