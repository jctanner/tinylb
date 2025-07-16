#!/usr/bin/env python3
"""
Standalone integration test for TinyLB Gateway API functionality.
This script runs the complete integration test flow without pytest.
"""

import sys
import os
import time
import traceback
import argparse
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Add the utils directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

# Import helper modules
try:
    import k8s_helpers
    import gateway_helpers
    import route_helpers

    print("✅ All helper modules imported successfully")
except Exception as e:
    print(f"❌ Failed to import helper modules: {e}")
    sys.exit(1)


def setup_k8s_client():
    """Set up Kubernetes client"""
    print("\n" + "=" * 60)
    print("🔧 Setting up Kubernetes client...")
    print("=" * 60)

    try:
        # Load kubeconfig
        config.load_kube_config()
        print("✅ Loaded kubeconfig successfully")

        # Create API clients
        core_client = client.CoreV1Api()
        apps_client = client.AppsV1Api()
        custom_client = client.CustomObjectsApi()
        extensions_client = client.ApiextensionsV1Api()

        k8s_client = {
            "core": core_client,
            "apps": apps_client,
            "custom": custom_client,
            "extensions": extensions_client,
        }

        print("✅ Created Kubernetes API clients")
        return k8s_client

    except Exception as e:
        print(f"❌ Failed to setup Kubernetes client: {e}")
        return None


def check_prerequisites(k8s_client):
    """Check that all prerequisites are met"""
    print("\n" + "=" * 60)
    print("🔍 Checking prerequisites...")
    print("=" * 60)

    success = True

    # Check TinyLB deployment
    print("\n1. Checking TinyLB deployment...")
    try:
        deployments = k8s_client["apps"].list_namespaced_deployment(
            namespace="tinylb-system"
        )
        tinylb_found = False
        for deployment in deployments.items:
            if "tinylb" in deployment.metadata.name:
                tinylb_found = True
                print(f"   ✅ Found TinyLB deployment: {deployment.metadata.name}")
                if deployment.status.ready_replicas == deployment.spec.replicas:
                    print("   ✅ TinyLB deployment is ready")
                else:
                    print("   ❌ TinyLB deployment is not ready")
                    success = False
                break

        if not tinylb_found:
            print(
                "   ⚠️  TinyLB deployment not found (this is expected if TinyLB is not deployed)"
            )
            print("   💡 The test will continue - TinyLB should be deployed separately")

    except Exception as e:
        print(f"   ❌ Failed to check TinyLB deployment: {e}")
        success = False

    # Check Gateway API CRDs
    print("\n2. Checking Gateway API CRDs...")
    try:
        crds = k8s_client["extensions"].list_custom_resource_definition()
        gateway_crds = [crd for crd in crds.items if "gateway" in crd.metadata.name]

        if len(gateway_crds) >= 2:
            print(f"   ✅ Found {len(gateway_crds)} Gateway API CRDs")
            for crd in gateway_crds:
                print(f"      - {crd.metadata.name}")
        else:
            print(
                f"   ❌ Found only {len(gateway_crds)} Gateway API CRDs (need at least 2)"
            )
            success = False

    except Exception as e:
        print(f"   ❌ Failed to check Gateway API CRDs: {e}")
        success = False

    # Check OpenShift Routes API
    print("\n3. Checking OpenShift Routes API...")
    try:
        routes = k8s_client["custom"].list_cluster_custom_object(
            group="route.openshift.io", version="v1", plural="routes", limit=1
        )
        print("   ✅ OpenShift Routes API is available")
    except Exception as e:
        print(f"   ❌ OpenShift Routes API not available: {e}")
        success = False

    return success


def create_test_namespace(k8s_client, namespace="gateway-api-test"):
    """Create a test namespace"""
    print(f"\n🏗️  Creating test namespace: {namespace}")

    try:
        # Check if namespace already exists
        try:
            existing = k8s_client["core"].read_namespace(name=namespace)
            print(f"   ✅ Namespace '{namespace}' already exists")
            return True
        except ApiException as e:
            if e.status != 404:
                raise

        # Create namespace
        namespace_spec = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)
        )
        k8s_client["core"].create_namespace(namespace_spec)
        print(f"   ✅ Created namespace: {namespace}")
        return True

    except Exception as e:
        print(f"   ❌ Failed to create namespace: {e}")
        return False


def run_gateway_api_test(k8s_client, namespace="gateway-api-test"):
    """Run the main Gateway API integration test"""
    print("\n" + "=" * 60)
    print("🧪 Running Gateway API integration test...")
    print("=" * 60)

    try:
        # Step 1: Create a Gateway
        print("\n1. Creating Gateway...")
        gateway_name = "test-gateway"
        gateway_spec = {
            "apiVersion": "gateway.networking.k8s.io/v1beta1",
            "kind": "Gateway",
            "metadata": {"name": gateway_name, "namespace": namespace},
            "spec": {
                "gatewayClassName": "istio",
                "listeners": [
                    {
                        "name": "http",
                        "hostname": "test-gateway.apps-crc.testing",
                        "port": 80,
                        "protocol": "HTTP",
                    },
                    {
                        "name": "https",
                        "hostname": "test-gateway.apps-crc.testing",
                        "port": 443,
                        "protocol": "TLS",
                        "tls": {"mode": "Passthrough"},
                    },
                ],
            },
        }

        k8s_client["custom"].create_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="gateways",
            body=gateway_spec,
        )
        print("   ✅ Created Gateway: test-gateway")

        # Step 2: Create a LoadBalancer service (simulating what Istio would do)
        print("\n2. Creating LoadBalancer service...")
        service_name = "test-gateway-istio"
        service_spec = client.V1Service(
            metadata=client.V1ObjectMeta(name=service_name, namespace=namespace),
            spec=client.V1ServiceSpec(
                type="LoadBalancer",
                ports=[
                    client.V1ServicePort(port=80, name="http"),
                    client.V1ServicePort(port=443, name="https"),
                ],
                selector={"app": "test-gateway"},
            ),
        )

        k8s_client["core"].create_namespaced_service(
            namespace=namespace, body=service_spec
        )
        print("   ✅ Created LoadBalancer service: test-gateway-istio")

        # Step 3: Wait for TinyLB to create a route
        print("\n3. Waiting for TinyLB to create route...")
        route_name = f"tinylb-{service_name}"
        route = None

        for attempt in range(60):  # Wait up to 60 seconds
            try:
                route = k8s_client["custom"].get_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=namespace,
                    plural="routes",
                    name=route_name,
                )
                print(f"   ✅ Route created: {route_name}")
                break
            except ApiException as e:
                if e.status == 404:
                    print(f"   ⏳ Waiting for route... (attempt {attempt + 1}/60)")
                    time.sleep(1)
                else:
                    raise

        if not route:
            print("   ❌ Route was not created within timeout")
            return False

        # Step 4: Verify route configuration
        print("\n4. Verifying route configuration...")

        # Check TinyLB labels
        labels = route.get("metadata", {}).get("labels", {})
        if labels.get("tinylb.io/managed") != "true":
            print("   ❌ Route missing tinylb.io/managed label")
            return False

        if labels.get("tinylb.io/service") != service_name:
            print("   ❌ Route has incorrect tinylb.io/service label")
            return False

        print("   ✅ Route has correct TinyLB labels")

        # Check TLS configuration
        spec = route.get("spec", {})
        tls = spec.get("tls", {})
        if tls.get("termination") != "passthrough":
            print("   ❌ Route has incorrect TLS termination")
            return False

        print("   ✅ Route has correct TLS configuration")

        # Check target service
        to = spec.get("to", {})
        if to.get("name") != service_name:
            print("   ❌ Route targets incorrect service")
            return False

        print("   ✅ Route targets correct service")

        # Step 5: Check that service gets external IP from route
        print("\n5. Checking service external IP...")

        # Wait for service to get external IP
        for attempt in range(30):
            service = k8s_client["core"].read_namespaced_service(
                name=service_name, namespace=namespace
            )

            if service.status.load_balancer.ingress:
                external_ip = service.status.load_balancer.ingress[0].hostname
                route_host = spec.get("host")

                if external_ip == route_host:
                    print(f"   ✅ Service has correct external IP: {external_ip}")
                    break
                else:
                    print(
                        f"   ❌ Service external IP ({external_ip}) doesn't match route host ({route_host})"
                    )
                    return False
            else:
                print(
                    f"   ⏳ Waiting for service external IP... (attempt {attempt + 1}/30)"
                )
                time.sleep(1)
        else:
            print("   ❌ Service did not get external IP within timeout")
            return False

        # Step 6: Check Gateway API integration (Gateway status should be updated by TinyLB)
        print("\n6. Checking Gateway API integration...")

        # Check if Gateway is marked as Accepted and Programmed
        gateway_issues = []

        for attempt in range(30):
            gateway = k8s_client["custom"].get_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="gateways",
                name=gateway_name,
            )

            status = gateway.get("status", {})
            conditions = status.get("conditions", [])
            addresses = status.get("addresses", [])

            # Check conditions
            accepted_status = None
            programmed_status = None

            for condition in conditions:
                if condition.get("type") == "Accepted":
                    accepted_status = condition.get("status")
                elif condition.get("type") == "Programmed":
                    programmed_status = condition.get("status")

            # Check if Gateway has been properly updated
            gateway_issues.clear()

            if accepted_status != "True":
                gateway_issues.append(
                    f"Gateway not Accepted (status: {accepted_status})"
                )

            if programmed_status != "True":
                gateway_issues.append(
                    f"Gateway not Programmed (status: {programmed_status})"
                )

            if not addresses:
                gateway_issues.append("Gateway has no addresses")
            else:
                # Check if address matches route hostname
                gateway_address = addresses[0].get("value")
                if gateway_address != route_host:
                    gateway_issues.append(
                        f"Gateway address ({gateway_address}) doesn't match route host ({route_host})"
                    )

            if not gateway_issues:
                print("   ✅ Gateway is properly Accepted and Programmed")
                print(f"   ✅ Gateway address: {gateway_address}")
                break
            else:
                print(
                    f"   ⏳ Waiting for Gateway API integration... (attempt {attempt + 1}/30)"
                )
                if attempt < 5:  # Show details for first few attempts
                    for issue in gateway_issues:
                        print(f"      - {issue}")
                time.sleep(1)
        else:
            print("   ❌ Gateway API integration FAILED within timeout")
            print("   Issues found:")
            for issue in gateway_issues:
                print(f"      - {issue}")
            print(
                "\n   💡 This suggests TinyLB is not functioning as a Gateway controller"
            )
            print("   💡 TinyLB should watch Gateway resources and update their status")
            return False

        print("\n🎉 Gateway API integration test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Gateway API integration test FAILED: {e}")
        traceback.print_exc()
        return False


def cleanup_test_resources(k8s_client, namespace="gateway-api-test"):
    """Clean up test resources"""
    try:
        print(f"   → Deleting namespace: {namespace}")
        k8s_client["core"].delete_namespace(name=namespace)
        print("   ✅ Cleanup completed")
        return True
    except Exception as e:
        print(f"   ❌ Cleanup failed: {e}")
        return False


def main():
    """Main test function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="TinyLB Gateway API integration test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python standalone_integration_test.py           # Run test and cleanup
  python standalone_integration_test.py --noclean # Run test but keep resources
        """,
    )
    parser.add_argument(
        "--noclean",
        action="store_true",
        help="Do not cleanup test resources after running (useful for debugging)",
    )

    args = parser.parse_args()

    print("🚀 Starting TinyLB Gateway API integration test...")

    # Setup
    k8s_client = setup_k8s_client()
    if not k8s_client:
        return 1

    # Check prerequisites
    if not check_prerequisites(k8s_client):
        print("\n❌ Prerequisites not met. Exiting.")
        return 1

    # Create test namespace
    namespace = "gateway-api-test"
    if not create_test_namespace(k8s_client, namespace):
        print("\n❌ Failed to create test namespace. Exiting.")
        return 1

    # Run the test
    test_passed = False
    try:
        test_passed = run_gateway_api_test(k8s_client, namespace)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        traceback.print_exc()

    # Cleanup
    if args.noclean:
        print(f"\n⚠️  Test resources left in namespace: {namespace}")
        print("💡 Use 'kubectl delete namespace gateway-api-test' to cleanup manually")
    else:
        print("\n🧹 Cleaning up test resources...")
        try:
            cleanup_test_resources(k8s_client, namespace)
        except Exception as e:
            print(f"⚠️  Cleanup failed: {e}")
            print(f"💡 You may need to manually cleanup namespace: {namespace}")

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    print("=" * 60)
    if test_passed:
        print("🎉 Integration test PASSED!")
        print("✅ TinyLB successfully created route for LoadBalancer service")
        print("✅ Gateway API integration is working correctly")
        return 0
    else:
        print("❌ Integration test FAILED!")
        print("💡 Check the output above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
