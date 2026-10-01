#include "catalogue-model.h"
#include "recent-model.h"

#include <QSignalSpy>
#include <QTest>

class CatalogueModelTests final : public QObject
{
    Q_OBJECT

private slots:
    void appliesUpdatesWithoutReset()
    {
        CatalogueModel model;
        QVERIFY(model.loadSnapshot(10, R"([{"game_id":"steam:1","title":"One","last_played":0}])"));
        QSignalSpy resetSpy(&model, &QAbstractItemModel::modelReset);
        QSignalSpy changedSpy(&model, &QAbstractItemModel::dataChanged);

        QVERIFY(model.applyChanges(10, R"([{"generation":11,"deltas":[{"kind":"update","game_id":"steam:1","changed_fields":["last_played"],"after":{"game_id":"steam:1","title":"One","last_played":99}}]}])"));
        QCOMPARE(model.generation(), qulonglong(11));
        QCOMPARE(model.rowCount(), 1);
        QCOMPARE(model.game(QStringLiteral("steam:1")).value(QStringLiteral("last_played")).toInt(), 99);
        QCOMPARE(resetSpy.count(), 0);
        QCOMPARE(changedSpy.count(), 1);
        QCOMPARE(changedSpy.at(0).at(2).value<QList<int>>(), QList<int>({CatalogueModel::LastPlayedRole}));
    }

    void appliesInsertAndRemoveWithStableIdentity()
    {
        CatalogueModel model;
        QVERIFY(model.loadSnapshot(20, R"([{"game_id":"steam:1","title":"One"}])"));
        QVERIFY(model.applyChanges(20, R"([{"generation":21,"deltas":[{"kind":"insert","game_id":"local:2","after":{"game_id":"local:2","title":"Two"}}]},{"generation":22,"deltas":[{"kind":"remove","game_id":"steam:1","before":{"game_id":"steam:1","title":"One"}}]}])"));
        QCOMPARE(model.generation(), qulonglong(22));
        QCOMPARE(model.rowCount(), 1);
        QVERIFY(model.game(QStringLiteral("steam:1")).isEmpty());
        QCOMPARE(model.game(QStringLiteral("local:2")).value(QStringLiteral("title")).toString(), QStringLiteral("Two"));
    }

    void recentMovesOneRowWithoutReset()
    {
        CatalogueModel source;
        RecentModel recent(&source);
        QVERIFY(source.loadSnapshot(30, R"([
            {"game_id":"steam:a","title":"A","install_state":"installed","last_played":30},
            {"game_id":"steam:b","title":"B","install_state":"installed","last_played":20},
            {"game_id":"steam:c","title":"C","install_state":"installed","last_played":10},
            {"game_id":"steam:x","title":"X","install_state":"installed","last_played":0}
        ])"));
        QSignalSpy resetSpy(&recent, &QAbstractItemModel::modelReset);
        QSignalSpy movedSpy(&recent, &QAbstractItemModel::rowsMoved);
        QVERIFY(source.applyChanges(30, R"([{"generation":31,"deltas":[{"kind":"update","game_id":"steam:c","changed_fields":["last_played"],"after":{"game_id":"steam:c","title":"C","install_state":"installed","last_played":40}}]}])"));
        QCOMPARE(recent.gameIdAt(0), QStringLiteral("steam:c"));
        QCOMPARE(recent.gameIdAt(1), QStringLiteral("steam:a"));
        QCOMPARE(recent.gameIdAt(2), QStringLiteral("steam:b"));
        QCOMPARE(resetSpy.count(), 0);
        QCOMPARE(movedSpy.count(), 1);
        QCOMPARE(recent.indexOfGame(QStringLiteral("steam:a")), 1);
        QCOMPARE(recent.indexOfGame(QStringLiteral("steam:x")), -1);
    }

    void recentEligibilityInsertsAndRemoves()
    {
        CatalogueModel source;
        RecentModel recent(&source);
        QVERIFY(source.loadSnapshot(40, R"([{"game_id":"steam:a","title":"A","install_state":"installed","last_played":10},{"game_id":"steam:b","title":"B","install_state":"installed","last_played":0}])"));
        QSignalSpy insertedSpy(&recent, &QAbstractItemModel::rowsInserted);
        QSignalSpy removedSpy(&recent, &QAbstractItemModel::rowsRemoved);
        QVERIFY(source.applyChanges(40, R"([{"generation":41,"deltas":[{"kind":"update","game_id":"steam:b","changed_fields":["last_played"],"after":{"game_id":"steam:b","title":"B","install_state":"installed","last_played":20}}]},{"generation":42,"deltas":[{"kind":"update","game_id":"steam:a","changed_fields":["last_played"],"after":{"game_id":"steam:a","title":"A","install_state":"installed","last_played":0}}]}])"));
        QCOMPARE(insertedSpy.count(), 1);
        QCOMPARE(removedSpy.count(), 1);
        QCOMPARE(recent.rowCount(), 1);
        QCOMPARE(recent.gameIdAt(0), QStringLiteral("steam:b"));
    }

    void recentHidesLinkedRommPresentationRow()
    {
        CatalogueModel source;
        RecentModel recent(&source);
        QVERIFY(source.loadSnapshot(43, R"([
            {"game_id":"local:ps2:1","provider":"local","install_state":"installed","last_played":20},
            {"game_id":"romm:228","provider":"romm","install_state":"installed","last_played":30,"installed_game_id":"local:ps2:1"}
        ])"));
        QCOMPARE(recent.rowCount(), 1);
        QCOMPARE(recent.gameIdAt(0), QStringLiteral("local:ps2:1"));
    }

    void recentExposesAtMostEightEntries()
    {
        CatalogueModel source;
        RecentModel recent(&source);
        QVERIFY(source.loadSnapshot(45, R"([
            {"game_id":"steam:1","install_state":"installed","last_played":10},
            {"game_id":"steam:2","install_state":"installed","last_played":20},
            {"game_id":"steam:3","install_state":"installed","last_played":30},
            {"game_id":"steam:4","install_state":"installed","last_played":40},
            {"game_id":"steam:5","install_state":"installed","last_played":50},
            {"game_id":"steam:6","install_state":"installed","last_played":60},
            {"game_id":"steam:7","install_state":"installed","last_played":70},
            {"game_id":"steam:8","install_state":"installed","last_played":80},
            {"game_id":"steam:9","install_state":"installed","last_played":90}
        ])"));
        QCOMPARE(recent.rowCount(), RecentModel::kMaximumEntries);
        QCOMPARE(recent.gameIdAt(0), QStringLiteral("steam:9"));
        QCOMPARE(recent.indexOfGame(QStringLiteral("steam:1")), -1);
        QCOMPARE(recent.gameIdAt(7), QStringLiteral("steam:2"));
    }

    void recentNonOrderingRoleDoesNotMove()
    {
        CatalogueModel source;
        RecentModel recent(&source);
        QVERIFY(source.loadSnapshot(50, R"([{"game_id":"steam:a","title":"A","install_state":"installed","last_played":10}])"));
        QSignalSpy movedSpy(&recent, &QAbstractItemModel::rowsMoved);
        QSignalSpy changedSpy(&recent, &QAbstractItemModel::dataChanged);
        QVERIFY(source.applyChanges(50, R"([{"generation":51,"deltas":[{"kind":"update","game_id":"steam:a","changed_fields":["title"],"after":{"game_id":"steam:a","title":"Renamed","install_state":"installed","last_played":10}}]}])"));
        QCOMPARE(movedSpy.count(), 0);
        QCOMPARE(changedSpy.count(), 1);
        QCOMPARE(recent.gameIdAt(0), QStringLiteral("steam:a"));
    }

    void recentRetainsLibraryMetadataRoles()
    {
        CatalogueModel source;
        RecentModel recent(&source);
        QVERIFY(source.loadSnapshot(60, R"([{"game_id":"steam:a","provider":"steam",
            "install_state":"installed","last_played":10,"genres":["Racing"],
            "game_modes":["Multiplayer"],"release_year":2020,
            "local_multiplayer":true,"online_multiplayer":false}])"));
        QCOMPARE(recent.rowCount(), 1);
        const QModelIndex item = recent.index(0, 0);
        QCOMPARE(recent.data(item, CatalogueModel::GenresRole).toStringList(),
                 QStringList({QStringLiteral("Racing")}));
        QCOMPARE(recent.data(item, CatalogueModel::GameModesRole).toList().size(), 1);
        QCOMPARE(recent.data(item, CatalogueModel::ReleaseYearRole).toInt(), 2020);
        QCOMPARE(recent.data(item, CatalogueModel::LocalMultiplayerRole).toBool(), true);
        QCOMPARE(recent.data(item, CatalogueModel::OnlineMultiplayerRole).toBool(), false);
    }
};

QTEST_MAIN(CatalogueModelTests)
#include "catalogue-model-test.moc"
