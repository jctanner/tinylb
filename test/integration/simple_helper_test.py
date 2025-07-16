#!/usr/bin/env python3
"""
Simple standalone test script to verify helper functions work and print statements are visible.
This script does NOT use pytest - just plain Python.
"""

import sys
import os

# Add the utils directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))


def test_helper_imports():
    """Test that we can import all helper modules"""
    print("=" * 60)
    print("🧪 Testing helper function imports...")
    print("=" * 60)

    try:
        print("📦 Importing k8s_helpers...")
        import k8s_helpers

        print("✅ k8s_helpers imported successfully")

        print("📦 Importing gateway_helpers...")
        import gateway_helpers

        print("✅ gateway_helpers imported successfully")

        print("📦 Importing route_helpers...")
        import route_helpers

        print("✅ route_helpers imported successfully")

        return k8s_helpers, gateway_helpers, route_helpers

    except Exception as e:
        print(f"❌ Import failed: {e}")
        return None, None, None


def test_helper_functions():
    """Test calling some helper functions to see if print statements work"""
    print("\n" + "=" * 60)
    print("🔧 Testing helper function calls...")
    print("=" * 60)

    k8s_helpers, gateway_helpers, route_helpers = test_helper_imports()

    if not all([k8s_helpers, gateway_helpers, route_helpers]):
        print("❌ Cannot test functions - imports failed")
        return False

    # Test some functions that don't require Kubernetes access
    print("\n🧪 Testing gateway_helpers.get_gateway_service_name()...")
    service_name = gateway_helpers.get_gateway_service_name("test-gateway", "istio")  # type: ignore
    print(f"   Result: {service_name}")

    print("\n🧪 Testing route_helpers.get_expected_route_hostname()...")
    hostname = route_helpers.get_expected_route_hostname("test-service", "test-namespace")  # type: ignore
    print(f"   Result: {hostname}")

    print(
        "\n🧪 Testing functions that would need k8s client (will fail, but should show print statements)..."
    )

    # These will fail because we don't have a k8s client, but should show print statements
    try:
        print("   → Calling k8s_helpers.get_service() with dummy client...")
        result = k8s_helpers.get_service(None, "test-namespace", "test-service")  # type: ignore
    except Exception as e:
        print(f"   Expected error: {e}")

    try:
        print("   → Calling gateway_helpers.get_gateway_address() with dummy client...")
        result = gateway_helpers.get_gateway_address(None, "test-namespace", "test-gateway")  # type: ignore
    except Exception as e:
        print(f"   Expected error: {e}")

    try:
        print("   → Calling route_helpers.get_route_for_gateway() with dummy client...")
        result = route_helpers.get_route_for_gateway(None, "test-namespace", "test-gateway")  # type: ignore
    except Exception as e:
        print(f"   Expected error: {e}")

    return True


def test_with_real_k8s():
    """Test with actual Kubernetes client if possible"""
    print("\n" + "=" * 60)
    print("🔧 Testing with real Kubernetes client...")
    print("=" * 60)

    try:
        print("📦 Setting up Kubernetes client...")
        from kubernetes import client, config

        # Try to load kubeconfig
        try:
            config.load_kube_config()
            print("✅ Loaded kubeconfig successfully")
        except Exception as e:
            print(f"❌ Failed to load kubeconfig: {e}")
            return False

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

        # Import helper modules
        k8s_helpers, gateway_helpers, route_helpers = test_helper_imports()

        if not all([k8s_helpers, gateway_helpers, route_helpers]):
            print("❌ Cannot test functions - imports failed")
            return False

        # Test some real API calls
        print("\n🧪 Testing real API calls...")

        print("   → Testing k8s_helpers.get_service() for non-existent service...")
        result = k8s_helpers.get_service(k8s_client, "default", "non-existent-service")  # type: ignore
        print(f"   Result: {result}")

        print("   → Testing k8s_helpers.get_route() for non-existent route...")
        result = k8s_helpers.get_route(k8s_client, "default", "non-existent-route")  # type: ignore
        print(f"   Result: {result}")

        print(
            "   → Testing gateway_helpers.get_gateway_address() for non-existent gateway..."
        )
        result = gateway_helpers.get_gateway_address(k8s_client, "default", "non-existent-gateway")  # type: ignore
        print(f"   Result: {result}")

        print(
            "   → Testing route_helpers.get_route_for_gateway() for non-existent gateway..."
        )
        result = route_helpers.get_route_for_gateway(k8s_client, "default", "non-existent-gateway")  # type: ignore
        print(f"   Result: {result}")

        return True

    except Exception as e:
        print(f"❌ Error setting up Kubernetes client: {e}")
        return False


def main():
    """Main test function"""
    print("🚀 Starting simple helper function test...")

    # Test 1: Import and basic function calls
    success1 = test_helper_functions()

    # Test 2: With real Kubernetes client
    success2 = test_with_real_k8s()

    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    print("=" * 60)
    print(f"✅ Helper function tests: {'PASSED' if success1 else 'FAILED'}")
    print(f"✅ Kubernetes client tests: {'PASSED' if success2 else 'FAILED'}")

    if success1 and success2:
        print(
            "\n🎉 All tests passed! Helper functions are working and print statements are visible."
        )
        return 0
    else:
        print("\n❌ Some tests failed. Check output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
