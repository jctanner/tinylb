"""
Gateway API specific helper functions for testing
"""

import time
from kubernetes import client

# Try relative import first (for pytest), then absolute import (for standalone)
try:
    from .k8s_helpers import (
        get_gateway,
        get_httproute,
        get_service,
        create_gateway,
        create_httproute,
    )
except ImportError:
    from k8s_helpers import (
        get_gateway,
        get_httproute,
        get_service,
        create_gateway,
        create_httproute,
    )


def is_gateway_programmed(k8s_client, namespace, gateway_name):
    """Check if a Gateway is in PROGRAMMED state"""
    print(
        f"🔍 [gateway_helpers.is_gateway_programmed] Checking if gateway '{gateway_name}' is programmed in namespace '{namespace}'"
    )
    gateway = get_gateway(k8s_client, namespace, gateway_name)
    if not gateway:
        return False

    status = gateway.get("status", {})
    conditions = status.get("conditions", [])

    for condition in conditions:
        if condition.get("type") == "Programmed":
            return condition.get("status") == "True"

    return False


def get_gateway_address(k8s_client, namespace, gateway_name):
    """Get the external address of a Gateway"""
    print(
        f"🔍 [gateway_helpers.get_gateway_address] Getting address for gateway '{gateway_name}' in namespace '{namespace}'"
    )
    gateway = get_gateway(k8s_client, namespace, gateway_name)
    if not gateway:
        return None

    status = gateway.get("status", {})
    addresses = status.get("addresses", [])

    if addresses:
        return addresses[0].get("value")

    return None


def wait_for_gateway_programmed(k8s_client, namespace, gateway_name, timeout=120):
    """Wait for a Gateway to become programmed"""
    print(
        f"⏳ [gateway_helpers.wait_for_gateway_programmed] Waiting for gateway '{gateway_name}' to be programmed (timeout: {timeout}s)"
    )
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_gateway_programmed(k8s_client, namespace, gateway_name):
            return True
        time.sleep(2)
    return False


def create_test_gateway(k8s_client, namespace, gateway_name, gateway_class="istio"):
    """Create a test Gateway with standard configuration"""
    print(
        f"➕ [gateway_helpers.create_test_gateway] Creating test gateway '{gateway_name}' with class '{gateway_class}' in namespace '{namespace}'"
    )
    gateway_spec = {
        "apiVersion": "gateway.networking.k8s.io/v1beta1",
        "kind": "Gateway",
        "metadata": {"name": gateway_name, "namespace": namespace},
        "spec": {
            "gatewayClassName": gateway_class,
            "listeners": [
                {
                    "name": "http",
                    "hostname": f"{gateway_name}.apps-crc.testing",
                    "port": 80,
                    "protocol": "HTTP",
                },
                {
                    "name": "https",
                    "hostname": f"{gateway_name}.apps-crc.testing",
                    "port": 443,
                    "protocol": "TLS",
                    "tls": {"mode": "Passthrough"},
                },
            ],
        },
    }

    return create_gateway(k8s_client, namespace, gateway_spec)


def create_test_httproute(
    k8s_client, namespace, httproute_name, gateway_name, backend_service_name
):
    """Create a test HTTPRoute that routes to a backend service"""
    print(
        f"➕ [gateway_helpers.create_test_httproute] Creating test httproute '{httproute_name}' for gateway '{gateway_name}' -> backend '{backend_service_name}' in namespace '{namespace}'"
    )
    httproute_spec = {
        "apiVersion": "gateway.networking.k8s.io/v1beta1",
        "kind": "HTTPRoute",
        "metadata": {"name": httproute_name, "namespace": namespace},
        "spec": {
            "parentRefs": [{"name": gateway_name}],
            "hostnames": [f"{gateway_name}.apps-crc.testing"],
            "rules": [
                {
                    "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
                    "backendRefs": [{"name": backend_service_name, "port": 8080}],
                }
            ],
        },
    }

    return create_httproute(k8s_client, namespace, httproute_spec)


def create_test_backend_service(k8s_client, namespace, service_name="echo-service"):
    """Create a test backend service and deployment"""
    print(
        f"➕ [gateway_helpers.create_test_backend_service] Creating test backend service '{service_name}' in namespace '{namespace}'"
    )
    # Try relative import first (for pytest), then absolute import (for standalone)
    try:
        from .k8s_helpers import create_service, create_deployment
    except ImportError:
        from k8s_helpers import create_service, create_deployment

    # Create deployment
    deployment_spec = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=service_name, namespace=namespace),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels={"app": service_name}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": service_name}),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="echo-server",
                            image="hashicorp/http-echo:0.2.3",
                            args=["-text=Hello from TinyLB Gateway API test!"],
                            ports=[client.V1ContainerPort(container_port=5678)],
                        )
                    ]
                ),
            ),
        ),
    )

    deployment = create_deployment(k8s_client, namespace, deployment_spec)

    # Create service
    service_spec = client.V1Service(
        metadata=client.V1ObjectMeta(name=service_name, namespace=namespace),
        spec=client.V1ServiceSpec(
            selector={"app": service_name},
            ports=[client.V1ServicePort(port=8080, target_port=5678, name="http")],
        ),
    )

    service = create_service(k8s_client, namespace, service_spec)

    return {"deployment": deployment, "service": service}


def wait_for_istio_service_creation(k8s_client, namespace, gateway_name, timeout=120):
    """Wait for Istio to create a LoadBalancer service for the Gateway"""
    print(
        f"⏳ [gateway_helpers.wait_for_istio_service_creation] Waiting for Istio service '{gateway_name}-istio' for gateway '{gateway_name}' (timeout: {timeout}s)"
    )
    expected_service_name = f"{gateway_name}-istio"
    start_time = time.time()

    while time.time() - start_time < timeout:
        service = get_service(k8s_client, namespace, expected_service_name)
        if service and service.spec.type == "LoadBalancer":
            return service
        time.sleep(2)

    return None


def get_gateway_service_name(gateway_name, gateway_class="istio"):
    """Get the expected service name for a Gateway"""
    print(
        f"🔍 [gateway_helpers.get_gateway_service_name] Getting expected service name for gateway '{gateway_name}' with class '{gateway_class}'"
    )
    if gateway_class == "istio":
        return f"{gateway_name}-istio"
    return f"{gateway_name}-{gateway_class}"


def test_http_request(hostname, timeout=30):
    """Test HTTP request to a Gateway endpoint"""
    print(f"🌐 [gateway_helpers.test_http_request] Testing HTTP request to '{hostname}' (timeout: {timeout}s)")
    
    import urllib.request
    import urllib.error
    
    url = f"http://{hostname}"
    
    try:
        request = urllib.request.Request(url)
        request.add_header('Host', hostname)
        
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_text = response.read().decode('utf-8')
            return response_text
    except urllib.error.HTTPError as e:
        print(f"   ❌ HTTP error {e.code}: {e.reason}")
        raise
    except Exception as e:
        print(f"   ❌ Connection error: {e}")
        raise


def wait_for_deployment_ready(k8s_client, namespace, deployment_name, timeout=120):
    """Wait for a deployment to become ready"""
    print(f"⏳ [gateway_helpers.wait_for_deployment_ready] Waiting for deployment '{deployment_name}' in namespace '{namespace}' (timeout: {timeout}s)")
    
    import time
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            deployment = k8s_client["apps"].read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )
            if (deployment.status.ready_replicas and 
                deployment.status.ready_replicas == deployment.spec.replicas):
                print(f"   ✅ Deployment '{deployment_name}' is ready")
                return True
                
        except Exception as e:
            print(f"   ⏳ Deployment not ready yet: {e}")
            
        time.sleep(2)
    
    print(f"   ❌ Deployment '{deployment_name}' did not become ready within {timeout}s")
    return False


def get_gateway_conditions(k8s_client, namespace, gateway_name):
    """Get all conditions for a Gateway"""
    print(
        f"🔍 [gateway_helpers.get_gateway_conditions] Getting conditions for gateway '{gateway_name}' in namespace '{namespace}'"
    )
    gateway = get_gateway(k8s_client, namespace, gateway_name)
    if not gateway:
        return []

    status = gateway.get("status", {})
    return status.get("conditions", [])


def print_gateway_status(k8s_client, namespace, gateway_name):
    """Print Gateway status for debugging"""
    print(
        f"📊 [gateway_helpers.print_gateway_status] Printing status for gateway '{gateway_name}' in namespace '{namespace}'"
    )
    gateway = get_gateway(k8s_client, namespace, gateway_name)
    if not gateway:
        print(f"Gateway {gateway_name} not found")
        return

    print(f"Gateway {gateway_name} status:")
    status = gateway.get("status", {})

    # Print addresses
    addresses = status.get("addresses", [])
    if addresses:
        print(f"  Addresses: {addresses}")
    else:
        print("  Addresses: None")

    # Print conditions
    conditions = status.get("conditions", [])
    if conditions:
        print("  Conditions:")
        for condition in conditions:
            print(f"    - Type: {condition.get('type')}")
            print(f"      Status: {condition.get('status')}")
            print(f"      Reason: {condition.get('reason')}")
            print(f"      Message: {condition.get('message')}")
    else:
        print("  Conditions: None")


def verify_gateway_route_integration(k8s_client, namespace, gateway_name):
    """Verify that Gateway address matches the Route hostname"""
    print(
        f"🔍 [gateway_helpers.verify_gateway_route_integration] Verifying integration between gateway '{gateway_name}' and its route in namespace '{namespace}'"
    )
    # Try relative import first (for pytest), then absolute import (for standalone)
    try:
        from .route_helpers import get_route_for_gateway
    except ImportError:
        from route_helpers import get_route_for_gateway

    gateway_address = get_gateway_address(k8s_client, namespace, gateway_name)
    if not gateway_address:
        return False

    route = get_route_for_gateway(k8s_client, namespace, gateway_name)
    if not route:
        return False

    route_host = route.get("spec", {}).get("host")
    return gateway_address == route_host
