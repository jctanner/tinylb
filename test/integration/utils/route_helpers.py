"""
OpenShift Route specific helper functions for testing
"""

import time

# Try relative import first (for pytest), then absolute import (for standalone)
try:
    from .k8s_helpers import get_route, list_routes_with_label
except ImportError:
    from k8s_helpers import get_route, list_routes_with_label


def get_route_for_gateway(k8s_client, namespace, gateway_name):
    """Get the TinyLB-created Route for a Gateway"""
    print(f"🔍 [route_helpers.get_route_for_gateway] Getting route for gateway '{gateway_name}' in namespace '{namespace}'")
    # Try relative import first (for pytest), then absolute import (for standalone)
    try:
        from .gateway_helpers import get_gateway_service_name
    except ImportError:
        from gateway_helpers import get_gateway_service_name

    service_name = get_gateway_service_name(gateway_name)
    route_name = f"tinylb-{service_name}"

    return get_route(k8s_client, namespace, route_name)


def get_route_for_service(k8s_client, namespace, service_name):
    """Get the TinyLB-created Route for a service"""
    print(f"🔍 [route_helpers.get_route_for_service] Getting route for service '{service_name}' in namespace '{namespace}'")
    route_name = f"tinylb-{service_name}"
    return get_route(k8s_client, namespace, route_name)


def wait_for_route_for_gateway(k8s_client, namespace, gateway_name, timeout=120):
    """Wait for TinyLB to create a Route for a Gateway"""
    print(f"⏳ [route_helpers.wait_for_route_for_gateway] Waiting for route creation for gateway '{gateway_name}' (timeout: {timeout}s)")
    start_time = time.time()
    while time.time() - start_time < timeout:
        route = get_route_for_gateway(k8s_client, namespace, gateway_name)
        if route:
            return route
        time.sleep(2)
    return None


def wait_for_route_for_service(k8s_client, namespace, service_name, timeout=120):
    """Wait for TinyLB to create a Route for a service"""
    print(f"⏳ [route_helpers.wait_for_route_for_service] Waiting for route creation for service '{service_name}' (timeout: {timeout}s)")
    start_time = time.time()
    while time.time() - start_time < timeout:
        route = get_route_for_service(k8s_client, namespace, service_name)
        if route:
            return route
        time.sleep(2)
    return None


def verify_route_configuration(route, expected_service_name):
    """Verify that a Route has the expected TinyLB configuration"""
    print(f"🔍 [route_helpers.verify_route_configuration] Verifying route configuration for expected service '{expected_service_name}'")
    if not route:
        return False

    spec = route.get("spec", {})
    metadata = route.get("metadata", {})

    # Check TinyLB labels
    labels = metadata.get("labels", {})
    if labels.get("tinylb.io/managed") != "true":
        return False

    if labels.get("tinylb.io/service") != expected_service_name:
        return False

    # Check TLS configuration
    tls = spec.get("tls", {})
    if tls.get("termination") != "passthrough":
        return False

    # Check target service
    to = spec.get("to", {})
    if to.get("name") != expected_service_name:
        return False

    return True


def get_route_hostname(route):
    """Get the hostname from a Route"""
    print(f"🔍 [route_helpers.get_route_hostname] Getting hostname from route")
    if not route:
        return None

    spec = route.get("spec", {})
    return spec.get("host")


def get_route_tls_termination(route):
    """Get the TLS termination type from a Route"""
    print(f"🔍 [route_helpers.get_route_tls_termination] Getting TLS termination from route")
    if not route:
        return None

    spec = route.get("spec", {})
    tls = spec.get("tls", {})
    return tls.get("termination")


def get_route_target_service(route):
    """Get the target service name from a Route"""
    print(f"🔍 [route_helpers.get_route_target_service] Getting target service from route")
    if not route:
        return None

    spec = route.get("spec", {})
    to = spec.get("to", {})
    return to.get("name")


def get_route_target_port(route):
    """Get the target port from a Route"""
    print(f"🔍 [route_helpers.get_route_target_port] Getting target port from route")
    if not route:
        return None

    spec = route.get("spec", {})
    port = spec.get("port", {})
    return port.get("targetPort")


def list_tinylb_routes(k8s_client, namespace):
    """List all Routes managed by TinyLB"""
    print(f"📋 [route_helpers.list_tinylb_routes] Listing all TinyLB-managed routes in namespace '{namespace}'")
    return list_routes_with_label(k8s_client, namespace, "tinylb.io/managed=true")


def print_route_status(k8s_client, namespace, route_name):
    """Print Route status for debugging"""
    print(f"📊 [route_helpers.print_route_status] Printing status for route '{route_name}' in namespace '{namespace}'")
    route = get_route(k8s_client, namespace, route_name)
    if not route:
        print(f"Route {route_name} not found")
        return

    print(f"Route {route_name} status:")

    # Print spec details
    spec = route.get("spec", {})
    print(f"  Host: {spec.get('host')}")
    print(f"  Target Service: {spec.get('to', {}).get('name')}")
    print(f"  Target Port: {spec.get('port', {}).get('targetPort')}")

    # Print TLS configuration
    tls = spec.get("tls", {})
    if tls:
        print(f"  TLS Termination: {tls.get('termination')}")
        print(f"  Insecure Edge Policy: {tls.get('insecureEdgeTerminationPolicy')}")

    # Print labels
    labels = route.get("metadata", {}).get("labels", {})
    tinylb_labels = {k: v for k, v in labels.items() if k.startswith("tinylb.io")}
    if tinylb_labels:
        print(f"  TinyLB Labels: {tinylb_labels}")

    # Print status
    status = route.get("status", {})
    ingress = status.get("ingress", [])
    if ingress:
        print(f"  Ingress Status: {ingress[0]}")


def verify_route_accessibility(route, expected_response_text=None):
    """Verify that a Route is accessible via HTTP"""
    print(f"🌐 [route_helpers.verify_route_accessibility] Verifying HTTP accessibility for route")
    import requests

    if not route:
        return False

    hostname = get_route_hostname(route)
    if not hostname:
        return False

    try:
        # Test HTTP access
        url = f"http://{hostname}"
        response = requests.get(url, timeout=10, verify=False)

        if response.status_code != 200:
            print(f"HTTP request to {url} failed with status {response.status_code}")
            return False

        if expected_response_text and expected_response_text not in response.text:
            print(
                f"Response text doesn't contain expected text: {expected_response_text}"
            )
            return False

        print(f"Successfully accessed {url}")
        return True

    except requests.RequestException as e:
        print(f"Failed to access {url}: {e}")
        return False


def verify_route_https_accessibility(route, expected_response_text=None):
    """Verify that a Route is accessible via HTTPS"""
    print(f"🔐 [route_helpers.verify_route_https_accessibility] Verifying HTTPS accessibility for route")
    import requests

    if not route:
        return False

    hostname = get_route_hostname(route)
    if not hostname:
        return False

    try:
        # Test HTTPS access
        url = f"https://{hostname}"
        response = requests.get(url, timeout=10, verify=False)

        if response.status_code != 200:
            print(f"HTTPS request to {url} failed with status {response.status_code}")
            return False

        if expected_response_text and expected_response_text not in response.text:
            print(
                f"Response text doesn't contain expected text: {expected_response_text}"
            )
            return False

        print(f"Successfully accessed {url} via HTTPS")
        return True

    except requests.RequestException as e:
        print(f"Failed to access {url} via HTTPS: {e}")
        return False


def get_expected_route_hostname(service_name, namespace):
    """Get the expected hostname for a TinyLB-created Route"""
    print(f"🔍 [route_helpers.get_expected_route_hostname] Getting expected hostname for service '{service_name}' in namespace '{namespace}'")
    return f"{service_name}-{namespace}.apps-crc.testing"


def verify_route_hostname_pattern(route, service_name, namespace):
    """Verify that Route hostname follows the expected pattern"""
    print(f"🔍 [route_helpers.verify_route_hostname_pattern] Verifying hostname pattern for service '{service_name}' in namespace '{namespace}'")
    if not route:
        return False

    actual_hostname = get_route_hostname(route)
    expected_hostname = get_expected_route_hostname(service_name, namespace)

    return actual_hostname == expected_hostname
