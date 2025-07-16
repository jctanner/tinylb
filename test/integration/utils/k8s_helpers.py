"""
Kubernetes helper functions for Gateway API integration testing
"""

import time
from kubernetes.client.rest import ApiException


def get_service(k8s_client, namespace, name):
    """Get a service by name"""
    print(
        f"🔍 [k8s_helpers.get_service] Getting service '{name}' in namespace '{namespace}'"
    )
    try:
        return k8s_client["core"].read_namespaced_service(
            name=name, namespace=namespace
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def get_deployment(k8s_client, namespace, name):
    """Get a deployment by name"""
    print(
        f"🔍 [k8s_helpers.get_deployment] Getting deployment '{name}' in namespace '{namespace}'"
    )
    try:
        return k8s_client["apps"].read_namespaced_deployment(
            name=name, namespace=namespace
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def get_route(k8s_client, namespace, name):
    """Get an OpenShift Route by name"""
    print(
        f"🔍 [k8s_helpers.get_route] Getting route '{name}' in namespace '{namespace}'"
    )
    try:
        return k8s_client["custom"].get_namespaced_custom_object(
            group="route.openshift.io",
            version="v1",
            namespace=namespace,
            plural="routes",
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def get_gateway(k8s_client, namespace, name):
    """Get a Gateway API Gateway by name"""
    print(
        f"🔍 [k8s_helpers.get_gateway] Getting gateway '{name}' in namespace '{namespace}'"
    )
    try:
        return k8s_client["custom"].get_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="gateways",
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def get_httproute(k8s_client, namespace, name):
    """Get a Gateway API HTTPRoute by name"""
    print(
        f"🔍 [k8s_helpers.get_httproute] Getting httproute '{name}' in namespace '{namespace}'"
    )
    try:
        return k8s_client["custom"].get_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="httproutes",
            name=name,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def create_service(k8s_client, namespace, service_spec):
    """Create a service"""
    service_name = (
        service_spec.metadata.name if hasattr(service_spec, "metadata") else "unknown"
    )
    print(
        f"➕ [k8s_helpers.create_service] Creating service '{service_name}' in namespace '{namespace}'"
    )
    return k8s_client["core"].create_namespaced_service(
        namespace=namespace, body=service_spec
    )


def create_deployment(k8s_client, namespace, deployment_spec):
    """Create a deployment"""
    deployment_name = (
        deployment_spec.metadata.name
        if hasattr(deployment_spec, "metadata")
        else "unknown"
    )
    print(
        f"➕ [k8s_helpers.create_deployment] Creating deployment '{deployment_name}' in namespace '{namespace}'"
    )
    return k8s_client["apps"].create_namespaced_deployment(
        namespace=namespace, body=deployment_spec
    )


def create_gateway(k8s_client, namespace, gateway_spec):
    """Create a Gateway API Gateway"""
    gateway_name = gateway_spec.get("metadata", {}).get("name", "unknown")
    print(
        f"➕ [k8s_helpers.create_gateway] Creating gateway '{gateway_name}' in namespace '{namespace}'"
    )
    return k8s_client["custom"].create_namespaced_custom_object(
        group="gateway.networking.k8s.io",
        version="v1beta1",
        namespace=namespace,
        plural="gateways",
        body=gateway_spec,
    )


def create_httproute(k8s_client, namespace, httproute_spec):
    """Create a Gateway API HTTPRoute"""
    httproute_name = httproute_spec.get("metadata", {}).get("name", "unknown")
    print(
        f"➕ [k8s_helpers.create_httproute] Creating httproute '{httproute_name}' in namespace '{namespace}'"
    )
    return k8s_client["custom"].create_namespaced_custom_object(
        group="gateway.networking.k8s.io",
        version="v1beta1",
        namespace=namespace,
        plural="httproutes",
        body=httproute_spec,
    )


def wait_for_service_external_ip(k8s_client, namespace, service_name, timeout=120):
    """Wait for a LoadBalancer service to get an external IP"""
    print(
        f"⏳ [k8s_helpers.wait_for_service_external_ip] Waiting for service '{service_name}' to get external IP (timeout: {timeout}s)"
    )
    start_time = time.time()
    while time.time() - start_time < timeout:
        service = get_service(k8s_client, namespace, service_name)
        if service and service.status.load_balancer.ingress:
            return service
        time.sleep(2)
    return None


def wait_for_deployment_ready(k8s_client, namespace, deployment_name, timeout=120):
    """Wait for a deployment to be ready"""
    print(
        f"⏳ [k8s_helpers.wait_for_deployment_ready] Waiting for deployment '{deployment_name}' to be ready (timeout: {timeout}s)"
    )
    start_time = time.time()
    while time.time() - start_time < timeout:
        deployment = get_deployment(k8s_client, namespace, deployment_name)
        if deployment and deployment.status.ready_replicas == deployment.spec.replicas:
            return deployment
        time.sleep(2)
    return None


def wait_for_route_creation(k8s_client, namespace, route_name, timeout=120):
    """Wait for an OpenShift Route to be created"""
    print(
        f"⏳ [k8s_helpers.wait_for_route_creation] Waiting for route '{route_name}' to be created (timeout: {timeout}s)"
    )
    start_time = time.time()
    while time.time() - start_time < timeout:
        route = get_route(k8s_client, namespace, route_name)
        if route:
            return route
        time.sleep(2)
    return None


def list_services_by_type(k8s_client, namespace, service_type="LoadBalancer"):
    """List services of a specific type"""
    print(
        f"📋 [k8s_helpers.list_services_by_type] Listing services of type '{service_type}' in namespace '{namespace}'"
    )
    services = k8s_client["core"].list_namespaced_service(namespace=namespace)
    return [svc for svc in services.items if svc.spec.type == service_type]


def list_routes_with_label(k8s_client, namespace, label_selector):
    """List OpenShift Routes with a specific label selector"""
    print(
        f"📋 [k8s_helpers.list_routes_with_label] Listing routes with label selector '{label_selector}' in namespace '{namespace}'"
    )
    try:
        routes = k8s_client["custom"].list_namespaced_custom_object(
            group="route.openshift.io",
            version="v1",
            namespace=namespace,
            plural="routes",
            label_selector=label_selector,
        )
        return routes.get("items", [])
    except ApiException as e:
        if e.status == 404:
            return []
        raise


def patch_service_status(k8s_client, namespace, service_name, status_patch):
    """Patch a service status (usually done by controllers)"""
    print(
        f"🔧 [k8s_helpers.patch_service_status] Patching status for service '{service_name}' in namespace '{namespace}'"
    )
    return k8s_client["core"].patch_namespaced_service_status(
        name=service_name, namespace=namespace, body=status_patch
    )


def get_pod_logs(k8s_client, namespace, pod_name, container=None):
    """Get logs from a pod"""
    container_info = f" container '{container}'" if container else ""
    print(
        f"📄 [k8s_helpers.get_pod_logs] Getting logs from pod '{pod_name}'{container_info} in namespace '{namespace}'"
    )
    try:
        return k8s_client["core"].read_namespaced_pod_log(
            name=pod_name, namespace=namespace, container=container
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def list_pods_by_label(k8s_client, namespace, label_selector):
    """List pods by label selector"""
    print(
        f"📋 [k8s_helpers.list_pods_by_label] Listing pods with label selector '{label_selector}' in namespace '{namespace}'"
    )
    pods = k8s_client["core"].list_namespaced_pod(
        namespace=namespace, label_selector=label_selector
    )
    return pods.items
