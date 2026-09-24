import QtQuick
import QtTest
import "../../ui"

TestCase {
    id: testCase
    name: "GameOptionsCandidates"

    QtObject {
        id: typography
        property string majorHeadingFamily: "sans-serif"
        property int majorHeadingWeight: Font.Bold
        property string displayFamily: "sans-serif"
        property int displayWeight: Font.Normal
        property string interfaceFamily: "sans-serif"
        function size(_role, fallback) { return fallback }
    }

    QtObject {
        id: palette
        property color overlayBackdrop: "#99000000"
        property color overlaySurface: "#202020"
        property color glassBorder: "#606060"
        property color headingAccent: "#ffffff"
        property color primaryText: "#ffffff"
        property color secondaryText: "#cccccc"
        property color warning: "#ffcc00"
        property color focusedCardSurface: "#404040"
        property color cardSurface: "#303030"
        property color focusIndicator: "#ffffff"
    }

    Item {
        id: scene
        width: 1280
        height: 720
        GameOptions {
            id: options
            anchors.fill: parent
            game: ({game_id: "steam:1", title: "Braid", canonical_title: "Braid"})
            view: "mapping"
            mappingResults: [{id: "2853", title: "Braid", year: 2008,
                              platforms: ["PC"], thumbnail: ""}]
            uiScale: 1
            typography: typography
            luluPalette: palette
        }
    }

    function init() {
        options.view = "mapping"
        options.mappingResults = [{id: "2853", title: "Braid", year: 2008,
                                   platforms: ["PC"], thumbnail: ""}]
        options.artworkCandidates = []
        options.selectedIndex = 0
    }

    function test_mapping_title_survives_missing_thumbnail_and_optional_fields() {
        tryCompare(findChild(options, "mappingCandidateTitle"), "text", "Braid")
        tryCompare(findChild(options, "mappingCandidateSubtitle"), "text", "2008 · PC")
    }

    function test_artwork_candidate_text_survives_missing_provenance_and_dimensions() {
        options.view = "artwork"
        options.artworkCandidates = [{id: "square-1", title: "Square candidate",
                                      thumbnail: "", url: "https://cdn.example/square.png"}]
        tryCompare(findChild(options, "artworkCandidateText"), "text", "Square candidate")
    }

    function test_mapping_selection_scrolls_through_stable_candidate_identity() {
        var candidates = []
        for (var index = 0; index < 18; index++)
            candidates.push({id: "igdb-" + index, title: "Candidate " + index,
                             year: 2000 + index, platforms: ["PC"], thumbnail: ""})
        options.mappingResults = candidates
        options.selectedIndex = 2
        var list = findChild(options, "mappingCandidateList")
        options.selectedIndex = candidates.length + 1
        options.ensureCandidateVisible()
        wait(50)
        tryVerify(function() { return list.contentY > 0 })
        compare(options.mappingResults[options.selectedIndex - 2].id, "igdb-17")
        compare(options.selectedCandidateId, "igdb-17")
        compare(options.selectedCandidate().id, "igdb-17")
        var refreshed = options.mappingResults.slice(0)
        refreshed[17] = {id: "igdb-17", title: "Candidate 17", year: 2017,
                         platforms: ["PC"],
                         thumbnail: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'%3E%3C/svg%3E"}
        options.mappingResults = refreshed
        wait(50)
        compare(options.selectedCandidate().id, "igdb-17")
        verify(list.itemAtIndex(17) !== null)
        verify(list.itemAtIndex(17).y + list.itemAtIndex(17).height
               <= list.contentY + list.height + 1)
        var reordered = options.mappingResults.slice(0).reverse()
        options.mappingResults = reordered
        wait(50)
        compare(options.selectedIndex, 2)
        compare(options.selectedCandidate().id, "igdb-17")
    }

    function test_artwork_selection_scrolls_without_rebinding_identity() {
        options.view = "artwork"
        var candidates = []
        for (var index = 0; index < 20; index++)
            candidates.push({id: "art-" + index, title: "Artwork " + index,
                             thumbnail: "", url: "https://cdn.example/" + index + ".jpg"})
        options.artworkCandidates = candidates
        options.selectedIndex = 0
        options.selectedIndex = candidates.length - 1
        options.ensureCandidateVisible()
        var list = findChild(options, "artworkCandidateList")
        wait(50)
        tryVerify(function() { return list.contentY > 0 })
        compare(options.artworkCandidates[options.selectedIndex].id, "art-19")
        compare(options.selectedCandidateId, "art-19")
        compare(options.selectedCandidate().id, "art-19")
        verify(list.itemAtIndex(19) !== null)
        verify(list.itemAtIndex(19).y + list.itemAtIndex(19).height
               <= list.contentY + list.height + 1)
    }
}
