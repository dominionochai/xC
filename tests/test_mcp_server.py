"""Tests for the optional MCP server."""
import importlib.util
import unittest

from backend import mcp_server


class TestMCPServer(unittest.TestCase):
    def test_module_imports(self):
        self.assertIsNotNone(mcp_server)

    def test_create_server_returns_none_when_mcp_sdk_is_unavailable(self):
        if importlib.util.find_spec("mcp") is not None:
            self.skipTest("MCP SDK is installed")
        self.assertIsNone(mcp_server.create_server())

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") is not None,
        "MCP SDK is not installed",
    )
    def test_create_server_when_mcp_sdk_is_installed(self):
        self.assertIsNotNone(mcp_server.create_server())

    @unittest.skip("Full FastMCP protocol integration requires a running transport")
    def test_fastmcp_protocol_integration(self):
        pass


if __name__ == "__main__":
    unittest.main()
