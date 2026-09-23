import QtQuick
import QtTest

TestCase {
    name: "RecentModelBoundary"
    property int selectedIndex: 0
    property string selectedGameId: recentRepeater.count > 0
        ? recentRepeater.itemAt(selectedIndex).gameRecord.game_id : ""

    function moveRecent(delta) {
        selectedIndex = Math.max(0, Math.min(recentRepeater.count - 1,
                                             selectedIndex + delta))
    }

    ListModel { id: nativeModelStandIn }

    Repeater {
        id: recentRepeater
        model: nativeModelStandIn
        delegate: Item {
            objectName: game_id
            property var gameRecord: ({
                game_id: game_id,
                title: title,
                artwork_url: artwork_url,
                platform: platform,
                provider: provider,
                last_played: last_played,
                genres: genres,
                game_modes: model.game_modes || [],
                game_mode: game_mode
            })
        }
    }

    function test_native_model_rows_create_visible_delegates() {
        compare(nativeModelStandIn.count, 0)
        compare(recentRepeater.count, 0)
        nativeModelStandIn.append({game_id: "steam:a", title: "Mario Kart 8 Deluxe",
                                    artwork_url: "file:///artwork.jpg", platform: "switch",
                                     provider: "local", last_played: 10, genres: ["Racing"],
                                     game_modes: ["Single player", "Multiplayer", "Split screen"],
                                     game_mode: "Multiplayer"})
        nativeModelStandIn.append({game_id: "steam:b", title: "Other Game",
                                    artwork_url: "file:///other.jpg", platform: "nes",
                                     provider: "steam", last_played: 9, genres: [],
                                     game_modes: [],
                                     game_mode: "Single player"})
        nativeModelStandIn.append({game_id: "steam:c", title: "Legacy Game",
                                    artwork_url: "file:///legacy.jpg", platform: "nes",
                                    provider: "steam", last_played: 8, genres: [],
                                    game_mode: "Single player"})
        compare(nativeModelStandIn.count, 3)
        compare(recentRepeater.count, 3)
        verify(recentRepeater.itemAt(0) !== null)
        verify(recentRepeater.itemAt(1) !== null)
        compare(recentRepeater.itemAt(0).gameRecord.title, "Mario Kart 8 Deluxe")
        verify(recentRepeater.itemAt(0).gameRecord.artwork_url.length > 0)
        compare(recentRepeater.itemAt(0).gameRecord.platform, "switch")
        compare(recentRepeater.itemAt(0).gameRecord.provider, "local")
        compare(recentRepeater.itemAt(0).gameRecord.game_modes,
                ["Single player", "Multiplayer", "Split screen"])
        compare(recentRepeater.itemAt(0).gameRecord.game_mode, "Multiplayer")
        compare(recentRepeater.itemAt(1).gameRecord.game_modes, [])
        compare(recentRepeater.itemAt(2).gameRecord.game_modes, [])
        compare(selectedGameId, "steam:a")
        moveRecent(1)
        compare(selectedIndex, 1)
        compare(selectedGameId, "steam:b")
    }
}
