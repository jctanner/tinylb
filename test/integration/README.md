# TinyLB Integration Tests

This directory contains pytest-based integration tests for TinyLB with Gateway API.

## Prerequisites

- Python 3.7+
- Access to a Kubernetes cluster with:
  - OpenShift Routes API (CRC, OpenShift, etc.)
  - Gateway API CRDs installed
  - TinyLB controller deployed

## Setup

1. Install Python dependencies:

   ```bash
   python3 run_tests.py --install-deps
   ```

2. Ensure your kubectl is configured to access the target cluster:

   ```bash
   kubectl cluster-info
   ```

3. Verify TinyLB is running:
   ```bash
   kubectl get pods -n tinylb-system
   ```

## Running Tests

### Quick Test Run (recommended)

```bash
python3 run_tests.py
```

### Run All Tests (including slow ones)

```bash
python3 run_tests.py --all
```

### Run with pytest directly

```bash
# Install dependencies first
pip install -r requirements.txt

# Run all tests
pytest test_gateway_api.py -v

# Run specific test class
pytest test_gateway_api.py::TestGatewayAPIIntegration -v

# Run specific test
pytest test_gateway_api.py::TestGatewayAPIIntegration::test_complete_gateway_api_flow -v
```

## Test Structure

```
test/integration/
├── conftest.py                    # pytest fixtures and configuration
├── test_gateway_api.py           # main integration tests
├── fixtures/                     # YAML test fixtures
│   ├── gateway.yaml
│   ├── httproute.yaml
│   └── backend-service.yaml
├── utils/                        # helper functions
│   ├── k8s_helpers.py           # Kubernetes client utilities
│   ├── gateway_helpers.py       # Gateway API specific helpers
│   └── route_helpers.py         # Route specific helpers
├── requirements.txt              # Python dependencies
├── pytest.ini                   # pytest configuration
└── README.md                    # this file
```

## Test Scenarios

### TestGatewayAPIIntegration

1. **test_prerequisites**: Verifies all prerequisites are met
2. **test_gateway_creation_basic**: Tests basic Gateway creation
3. **test_complete_gateway_api_flow**: Full end-to-end test of Gateway API + TinyLB
4. **test_route_configuration_details**: Verifies Route configuration details
5. **test_port_selection_priority**: Tests TinyLB's port selection algorithm
6. **test_service_cleanup**: Tests cleanup when services are deleted

### TestTinyLBController

1. **test_tinylb_controller_running**: Verifies TinyLB controller is running
2. **test_tinylb_rbac_permissions**: Verifies RBAC permissions

## Expected Test Flow

1. **Setup**: Create test namespace and verify prerequisites
2. **Resource Creation**: Create Gateway, HTTPRoute, and backend service
3. **Service Simulation**: Create mock LoadBalancer service (simulates Istio)
4. **TinyLB Processing**: Wait for TinyLB to create Route and update service status
5. **Verification**: Verify Gateway becomes programmed and Route is accessible
6. **Cleanup**: Clean up all test resources

## Troubleshooting

### Common Issues

**TinyLB not running**

```bash
kubectl get pods -n tinylb-system
kubectl logs -n tinylb-system deployment/tinylb-controller-manager
```

**Gateway API CRDs not installed**

```bash
kubectl get crd | grep gateway
```

**OpenShift Routes not available**

```bash
kubectl get crd | grep route
```

### Debug Mode

Run tests with debug output:

```bash
pytest test_gateway_api.py -v -s --tb=long
```

### Check Test Resources

During test run, you can check created resources:

```bash
kubectl get all -n gateway-api-test
kubectl get gateway -n gateway-api-test
kubectl get httproute -n gateway-api-test
kubectl get route -n gateway-api-test
```

## Integration with CI/CD

Add to your CI/CD pipeline:

```yaml
- name: Run TinyLB Integration Tests
  run: |
    cd test/integration
    python3 run_tests.py --install-deps
    python3 run_tests.py
```

## Contributing

When adding new tests:

1. Follow the existing test patterns in `test_gateway_api.py`
2. Use appropriate fixtures from `conftest.py`
3. Add helper functions to the `utils/` directory
4. Update this README with new test scenarios
5. Ensure tests clean up resources properly

## Notes

- Tests create resources in the `gateway-api-test` namespace
- Mock LoadBalancer services are created to simulate Istio behavior
- Tests focus on TinyLB functionality rather than full Istio installation
- External HTTP/HTTPS testing may require proper DNS/networking setup
