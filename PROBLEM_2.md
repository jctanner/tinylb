# PROBLEM_2: TinyLB Gateway Controller Missing - Gateway Status Not Updated

## Problem Statement

**TinyLB is missing Gateway controller functionality**, causing Gateway API Gateways to remain in `PROGRAMMED: False` state even when TinyLB successfully creates OpenShift Routes for their LoadBalancer services.

## Issue Discovery

This bug was discovered through the integration test in PROBLEM_1. The test revealed that TinyLB has:

✅ **Working Service Controller** - Creates routes for LoadBalancer services  
❌ **Missing Gateway Controller** - Does not watch or update Gateway resources

## Current Behavior (Bug)

When a Gateway API Gateway is created with `gatewayClassName: istio`:

1. **Gateway remains in Unknown state:**

   ```yaml
   status:
     conditions:
       - lastTransitionTime: "1970-01-01T00:00:00Z"
         message: Waiting for controller
         reason: Pending
         status: Unknown
         type: Accepted
       - lastTransitionTime: "1970-01-01T00:00:00Z"
         message: Waiting for controller
         reason: Pending
         status: Unknown
         type: Programmed
   ```

2. **Gateway has no addresses:**

   ```yaml
   status:
     addresses: [] # Empty - should contain route hostname
   ```

3. **LoadBalancer service gets external IP but Gateway doesn't reflect this:**

   ```bash
   # Service gets external IP (✅ Working)
   kubectl get svc test-gateway-istio
   NAME                 EXTERNAL-IP
   test-gateway-istio   test-gateway-istio-gateway-api-test.apps-crc.testing

   # Gateway shows no address (❌ Bug)
   kubectl get gateway test-gateway
   NAME           CLASS   ADDRESS   PROGRAMMED   AGE
   test-gateway   istio   (none)    Unknown      5m
   ```

## Expected Behavior (Fix)

After implementing the Gateway controller, the Gateway should show:

```yaml
status:
  addresses:
    - type: Hostname
      value: test-gateway-istio-gateway-api-test.apps-crc.testing
  conditions:
    - lastTransitionTime: "2025-07-16T16:45:00Z"
      message: Gateway is accepted
      reason: Accepted
      status: "True"
      type: Accepted
    - lastTransitionTime: "2025-07-16T16:45:00Z"
      message: Gateway is programmed
      reason: Programmed
      status: "True"
      type: Programmed
```

And kubectl should show:

```bash
kubectl get gateway test-gateway
NAME           CLASS   ADDRESS                                        PROGRAMMED   AGE
test-gateway   istio   test-gateway-istio-gateway-api-test.apps-crc.testing  True         5m
```

## Root Cause Analysis

### What TinyLB Currently Does (Service Controller)

TinyLB implements a **Service controller** in `internal/controller/service_controller.go` that:

1. ✅ Watches LoadBalancer services
2. ✅ Creates OpenShift Routes for LoadBalancer services
3. ✅ Updates LoadBalancer service status with external hostname
4. ✅ Manages Route lifecycle (create, update, delete)
5. ✅ Handles TLS passthrough configuration
6. ✅ Selects appropriate ports (443, 80, etc.)

### What TinyLB is Missing (Gateway Controller)

TinyLB does **NOT** implement a **Gateway controller** that:

1. ❌ Watches Gateway resources with specific `gatewayClassName` (e.g., `istio`)
2. ❌ Updates Gateway status conditions (`Accepted`, `Programmed`)
3. ❌ Populates Gateway `status.addresses` field
4. ❌ Links Gateway resources to their corresponding LoadBalancer services
5. ❌ Handles Gateway lifecycle events

## Technical Implementation Requirements

### 1. Gateway Controller Structure

Create `internal/controller/gateway_controller.go` with:

```go
type GatewayReconciler struct {
    client.Client
    Scheme *runtime.Scheme

    // Configuration
    SupportedGatewayClasses []string  // e.g., ["istio"]
    RouteNamespace          string    // OpenShift route namespace
}

func (r *GatewayReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    // Implementation needed
}
```

### 2. Gateway Watching Logic

The controller should:

1. **Watch Gateway resources** with supported `gatewayClassName`
2. **Filter by gatewayClassName** - only process supported classes (e.g., `istio`)
3. **Find associated LoadBalancer service** using naming convention
4. **Check if Route exists** for the LoadBalancer service
5. **Update Gateway status** based on Route availability

### 3. Gateway Status Updates

#### Gateway Accepted Condition

```go
func (r *GatewayReconciler) updateGatewayAcceptedCondition(ctx context.Context, gateway *gatewayv1.Gateway, accepted bool, reason, message string) error {
    condition := metav1.Condition{
        Type:               string(gatewayv1.GatewayConditionAccepted),
        Status:             metav1.ConditionTrue,  // or False
        Reason:             reason,
        Message:            message,
        LastTransitionTime: metav1.Now(),
    }

    meta.SetStatusCondition(&gateway.Status.Conditions, condition)
    return r.Status().Update(ctx, gateway)
}
```

#### Gateway Programmed Condition

```go
func (r *GatewayReconciler) updateGatewayProgrammedCondition(ctx context.Context, gateway *gatewayv1.Gateway, programmed bool, reason, message string) error {
    condition := metav1.Condition{
        Type:               string(gatewayv1.GatewayConditionProgrammed),
        Status:             metav1.ConditionTrue,  // or False
        Reason:             reason,
        Message:            message,
        LastTransitionTime: metav1.Now(),
    }

    meta.SetStatusCondition(&gateway.Status.Conditions, condition)
    return r.Status().Update(ctx, gateway)
}
```

#### Gateway Addresses

```go
func (r *GatewayReconciler) updateGatewayAddresses(ctx context.Context, gateway *gatewayv1.Gateway, hostname string) error {
    gateway.Status.Addresses = []gatewayv1.GatewayStatusAddress{
        {
            Type:  gatewayv1.HostnameAddressType,
            Value: hostname,
        },
    }
    return r.Status().Update(ctx, gateway)
}
```

### 4. Service-Gateway Association

The controller needs to determine the LoadBalancer service name for a Gateway. Based on current TinyLB behavior, this appears to follow the pattern:

```go
func getLoadBalancerServiceName(gateway *gatewayv1.Gateway, gatewayClassName string) string {
    // For istio class, the pattern seems to be: {gateway-name}-istio
    if gatewayClassName == "istio" {
        return fmt.Sprintf("%s-istio", gateway.Name)
    }
    return fmt.Sprintf("%s-%s", gateway.Name, gatewayClassName)
}
```

### 5. Controller Manager Integration

Update `cmd/main.go` to register the Gateway controller:

```go
import (
    gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"
)

func main() {
    // ... existing code ...

    // Add Gateway API scheme
    utilruntime.Must(gatewayv1.AddToScheme(scheme))

    // ... existing service controller setup ...

    // Add Gateway controller
    if err = (&controllers.GatewayReconciler{
        Client:                  mgr.GetClient(),
        Scheme:                  mgr.GetScheme(),
        SupportedGatewayClasses: []string{"istio"}, // configurable
        RouteNamespace:          "", // same namespace as gateway
    }).SetupWithManager(mgr); err != nil {
        setupLog.Error(err, "unable to create controller", "controller", "Gateway")
        os.Exit(1)
    }
}
```

## Integration Test Validation

The integration test in `test/integration/standalone_integration_test.py` already validates this functionality. Once the Gateway controller is implemented, the test should pass the "Gateway API integration" step:

```bash
6. Checking Gateway API integration...
   ✅ Gateway is properly Accepted and Programmed
   ✅ Gateway address: test-gateway-istio-gateway-api-test.apps-crc.testing
```

## Implementation Steps

### Phase 1: Basic Gateway Controller

1. **Create Gateway controller structure**

   - `internal/controller/gateway_controller.go`
   - Basic reconciliation loop
   - Gateway watching with gatewayClassName filter

2. **Add Gateway API dependencies**

   - Update `go.mod` with Gateway API imports
   - Add Gateway API scheme to controller manager

3. **Implement basic status updates**
   - Accept condition (always True for supported classes)
   - Programmed condition (based on Route existence)

### Phase 2: Service-Gateway Association

1. **Implement service name resolution**

   - Map Gateway to expected LoadBalancer service name
   - Handle different gatewayClassName patterns

2. **Add Route existence checking**

   - Check if TinyLB created Route for the service
   - Validate Route configuration

3. **Implement address population**
   - Set Gateway addresses from Route hostname
   - Handle address updates when Route changes

### Phase 3: Advanced Features

1. **Error handling and validation**

   - Handle missing services gracefully
   - Validate Gateway configuration
   - Report meaningful error messages

2. **Lifecycle management**

   - Handle Gateway deletion
   - Clean up resources when needed
   - Watch for Service/Route changes

3. **Configuration options**
   - Configurable supported gateway classes
   - Customizable service naming patterns

## Testing Strategy

### Unit Tests

Create unit tests for:

- Gateway controller reconciliation logic
- Service name resolution
- Status condition updates
- Address population

### Integration Tests

The existing integration test (`standalone_integration_test.py`) will validate:

- End-to-end Gateway API integration
- Gateway status updates
- Service-Route-Gateway association

### Manual Testing

Test scenarios:

1. **Basic Gateway creation** - Gateway with istio class
2. **Service creation order** - Gateway before/after LoadBalancer service
3. **Route lifecycle** - Route creation, update, deletion
4. **Multiple Gateways** - Multiple Gateways in same namespace
5. **Error conditions** - Missing services, invalid configurations

## Success Criteria

### Primary Success Criteria

1. **Gateway Accepted Status** - Gateway shows `Accepted: True`
2. **Gateway Programmed Status** - Gateway shows `Programmed: True`
3. **Gateway Address Population** - Gateway shows correct hostname
4. **Integration Test Passes** - `standalone_integration_test.py` succeeds

### Secondary Success Criteria

1. **Error Handling** - Graceful handling of missing services
2. **Performance** - Efficient reconciliation without excessive API calls
3. **Observability** - Proper logging and metrics
4. **Documentation** - Clear code documentation

## Current Status

- [ ] Gateway controller implementation
- [ ] Service-Gateway association logic
- [ ] Status condition updates
- [ ] Address population
- [ ] Integration test validation
- [ ] Documentation updates

## References

- **Gateway API Specification:** https://gateway-api.sigs.k8s.io/
- **TinyLB Service Controller:** `internal/controller/service_controller.go`
- **Integration Test:** `test/integration/standalone_integration_test.py`
- **PROBLEM_1 Resolution:** Shows Service controller works, Gateway controller missing

---

_This document will be updated as we progress through the implementation._
