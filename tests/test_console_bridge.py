import asyncio
import importlib.util
import http.client
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("console_ui_bridge", ROOT / "scripts" / "console-ui-bridge.py")
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


class ConsoleBridgeTests(unittest.TestCase):
    def test_bridge_checks_all_prerequisites_before_launch(self) -> None:
        class ReadyBus:
            def __init__(self) -> None:
                self.calls = []

            async def introspect(self, name: str, path: str) -> object:
                self.calls.append((name, path))
                return object()

        bus = ReadyBus()
        result = asyncio.run(BRIDGE.introspect_lulu_services(bus))
        self.assertEqual(set(result), {"sessiond", "consoled", "acquisitiond"})
        self.assertEqual(len(bus.calls), 3)

    def test_launch_path_decodes_qml_encoded_game_id(self) -> None:
        path = "/launch/steam%3A220780"
        self.assertEqual(BRIDGE.unquote(path.removeprefix("/launch/")), "steam:220780")

    def test_launch_call_has_a_provider_watchdog_timeout(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn("timeout = None if game_id.startswith(\"steam:\") else 15", source)
        self.assertIn("str(error) or type(error).__name__", source)

    def test_state_path_reads_authoritative_session_state(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn('if urlparse(self.path).path == "/state":', source)
        self.assertIn("call_get_state()", source)

    def test_metadata_options_paths_use_the_service_boundary(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        for path in ("/metadata/search", "/metadata/match/", "/metadata/title/", "/metadata/artwork/"):
            self.assertIn(path, source)
        for method_name in ("call_search_metadata", "call_set_metadata_match", "call_set_title_override",
                            "call_clear_title_override", "call_suppress_artwork", "call_restore_artwork"):
            self.assertIn(method_name, source)


    def test_launch_endpoint_returns_bridge_result_without_double_wrap(self) -> None:
        class Logs:
            def start(self, game_id: str) -> None:
                pass

            def note(self, source: str, line: str) -> None:
                pass

        class FakeBridge:
            launch_logs = Logs()

            def call(self, operation, timeout=None):
                return asyncio.run(operation)

            async def launch_game(self, game_id: str) -> dict[str, object]:
                self.asserted_game_id = game_id
                return {"token": "transaction-token", "navigation_only": False}

        fake = FakeBridge()
        previous = getattr(BRIDGE.ApiHandler, "bridge", None)
        BRIDGE.ApiHandler.bridge = fake
        server = BRIDGE.ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.ApiHandler)
        thread = BRIDGE.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("POST", "/launch/steam%3A40800")
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            if previous is None:
                del BRIDGE.ApiHandler.bridge
            else:
                BRIDGE.ApiHandler.bridge = previous

        self.assertEqual(response.status, 200)
        self.assertIsInstance(body["token"], str)
        self.assertEqual(body["token"], "transaction-token")
        self.assertIs(body["navigation_only"], False)
        self.assertNotIsInstance(body["token"], dict)
        self.assertEqual(fake.asserted_game_id, "steam:40800")

    def test_steam_game_uses_session_transaction_not_navigation_only_uri(self) -> None:
        class Session:
            async def call_request_steam_launch(self, appid: str, timeout: int) -> str:
                return BRIDGE.Variant("s", "transaction-token")

        class Consoled:
            async def call_launch_game(self, game_id: str, timeout: int) -> str:
                raise AssertionError("Steam launch bypassed sessiond")

        async def exercise() -> None:
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), Consoled(), Session())
            result = await bridge.launch_game("steam:40800")
            self.assertIsInstance(result["token"], str)
            self.assertEqual(json.loads(json.dumps(result))["token"], "transaction-token")
            self.assertEqual(result, {"token": "transaction-token", "navigation_only": False})

        asyncio.run(exercise())

    def test_local_cancellation_uses_consoled_process_boundary(self) -> None:
        class Session:
            async def call_cancel_launch(self) -> None:
                raise AssertionError("local cancellation bypassed consoled")

        class Consoled:
            async def call_cancel_local_launch(self) -> None:
                self.cancelled = True

        async def exercise() -> None:
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, Session())
            bridge.local_token = "local:123"
            await bridge.cancel_launch()
            self.assertTrue(consoled.cancelled)
            self.assertIsNone(bridge.local_token)

        asyncio.run(exercise())

    def test_cancellation_log_entry_is_emitted_once(self) -> None:
        class Session:
            async def call_cancel_launch(self) -> None:
                return

        async def exercise() -> None:
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), Session())
            bridge.launch_logs._active = True
            await asyncio.gather(bridge.cancel_launch(), bridge.cancel_launch(), bridge.cancel_launch())
            lines = bridge.launch_logs.snapshot()["lines"]
            self.assertEqual(sum("Cancelling launch" in line for line in lines), 1)

        asyncio.run(exercise())

if __name__ == "__main__":
    unittest.main()
