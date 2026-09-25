import QtQuick
import QtTest
import "../../ui" as UI

TestCase {
    name: "LibraryList"
    width: 1280
    height: 720
    when: windowShown

    UI.LuluPalette { id: palette }
    UI.LibrarySpace {
        id: library
        width: 1280
        height: 720
        luluPalette: palette
        canonicalGames: []
    }

    function test_selection_scrolls_in_complete_rows() {
        var games = []
        for (var i = 0; i < 30; ++i)
            games.push({game_id: "steam:" + i, title: "Game " + i, platform: "pc"})
        library.canonicalGames = games
        wait(1)
        var rows = findChild(library, "libraryGameRows")
        verify(rows !== null)
        verify(rows.height / library.rowHeight <= 8)
        compare(rows.height % library.rowHeight, 0)
        for (var j = 1; j < games.length; ++j) {
            library.moveGame(1)
            wait(1)
            compare(library.selectedIndex, j)
            compare(rows.currentIndex, j)
            verify(j * library.rowHeight >= rows.contentY)
            verify((j + 1) * library.rowHeight <= rows.contentY + rows.height)
        }
        library.moveGame(1)
        compare(library.selectedIndex, 29)
        library.moveGame(-1)
        compare(library.selectedIndex, 28)
    }
}
