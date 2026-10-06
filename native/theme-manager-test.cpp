#include "theme-manager.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QTemporaryDir>
#include <QUrl>
#include <QtTest>

static bool copyTree(const QString &source, const QString &target)
{
    QDir().mkpath(target);
    QDir dir(source);
    for (const QFileInfo &entry : dir.entryInfoList(QDir::Files | QDir::Dirs | QDir::NoDotAndDotDot)) {
        const QString destination = QDir(target).filePath(entry.fileName());
        if (entry.isDir()) {
            if (!copyTree(entry.filePath(), destination)) return false;
        } else if (!QFile::copy(entry.filePath(), destination)) return false;
    }
    return true;
}

class ThemeManagerTest final : public QObject
{
    Q_OBJECT
private slots:
    void discoveryUsesCompleteValidationAndMigratesLegacySelection()
    {
        QTemporaryDir temp;
        QVERIFY(temp.isValid());
        const QString root = QDir(temp.path()).filePath("themes");
        QVERIFY(copyTree(QStringLiteral(THEME_SOURCE_DIR) + "/modern", root + "/modern"));
        QVERIFY(copyTree(QStringLiteral(THEME_SOURCE_DIR) + "/95", root + "/95"));

        const QString bad = root + "/invalid";
        QVERIFY(copyTree(root + "/95", bad));
        QFile file(bad + "/theme.json");
        QVERIFY(file.open(QIODevice::ReadOnly));
        QJsonObject json = QJsonDocument::fromJson(file.readAll()).object();
        file.close();
        json.insert("id", "invalid");
        QJsonObject icons = json.value("icons").toObject();
        icons.insert("settings", "../outside.svg");
        json.insert("icons", icons);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        file.write(QJsonDocument(json).toJson());
        file.close();

        const QString outsideSvg = temp.path() + "/outside.svg";
        QFile outsideFile(outsideSvg);
        QVERIFY(outsideFile.open(QIODevice::WriteOnly));
        outsideFile.write("<svg xmlns=\"http://www.w3.org/2000/svg\"/>");
        outsideFile.close();
        QVERIFY(copyTree(root + "/95", root + "/escaped"));
        QFile escapedConfig(root + "/escaped/theme.json");
        QVERIFY(escapedConfig.open(QIODevice::ReadOnly));
        QJsonObject escapedJson = QJsonDocument::fromJson(escapedConfig.readAll()).object();
        escapedConfig.close();
        escapedJson.insert("id", "escaped");
        QVERIFY(escapedConfig.open(QIODevice::WriteOnly | QIODevice::Truncate));
        escapedConfig.write(QJsonDocument(escapedJson).toJson());
        escapedConfig.close();
        QVERIFY(QFile::remove(root + "/escaped/icons/settings.svg"));
        QVERIFY(QFile::link(outsideSvg, root + "/escaped/icons/settings.svg"));

        QVERIFY(copyTree(root + "/95", root + "/bad-svg"));
        QFile badSvgConfig(root + "/bad-svg/theme.json");
        QVERIFY(badSvgConfig.open(QIODevice::ReadOnly));
        QJsonObject badSvgJson = QJsonDocument::fromJson(badSvgConfig.readAll()).object();
        badSvgConfig.close();
        badSvgJson.insert("id", "bad-svg");
        QVERIFY(badSvgConfig.open(QIODevice::WriteOnly | QIODevice::Truncate));
        badSvgConfig.write(QJsonDocument(badSvgJson).toJson());
        badSvgConfig.close();
        QFile brokenSvg(root + "/bad-svg/icons/settings.svg");
        QVERIFY(brokenSvg.open(QIODevice::WriteOnly | QIODevice::Truncate));
        brokenSvg.write("<svg><broken></svg>");
        brokenSvg.close();

        qputenv("MUDOS_THEME_ROOTS", root.toUtf8());
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope,
                           QDir(temp.path()).filePath("settings"));
        QSettings saved(QSettings::IniFormat, QSettings::UserScope, "Mudos", "lulu");
        saved.setValue("appearance/theme", "mudos-default");
        saved.sync();

        ThemeManager manager;
        QCOMPARE(manager.activeId(), QStringLiteral("modern"));
        QCOMPARE(manager.activeName(), QStringLiteral("Modern"));
        QCOMPARE(saved.value("appearance/theme").toString(), QStringLiteral("modern"));
        QStringList ids;
        for (const QVariant &theme : manager.themes()) ids.append(theme.toMap().value("id").toString());
        QCOMPARE(ids, QStringList({"modern", "95"}));
        QVERIFY(!ids.contains("mudos-default"));
        QVERIFY(!ids.contains("invalid"));
        QVERIFY(!ids.contains("escaped"));
        QVERIFY(!ids.contains("bad-svg"));

        QVERIFY(manager.select("95"));
        QCOMPARE(manager.activeName(), QStringLiteral("95"));
        QCOMPARE(manager.glass().value("enabled").toBool(), false);
        QCOMPARE(manager.radii().value("panel").toDouble(), 0.0);
        QVERIFY(manager.wallpaperShader().contains("themes/95/wallpaper/wallpaper.frag.qsb"));
        QVERIFY(manager.fonts().value("regular").toString().contains("themes/95/fonts/"));
        QVERIFY(manager.iconUrl("settings").contains("themes/95/icons/settings.svg"));
        QCOMPARE(saved.value("appearance/theme").toString(), QStringLiteral("95"));
        QVERIFY(manager.select("modern"));
        QCOMPARE(manager.colors().value("backdrop").toString(), QStringLiteral("#060607"));
        ThemeManager guideAndNotificationManager;
        QCOMPARE(guideAndNotificationManager.activeId(), QStringLiteral("modern"));
        saved.setValue("appearance/theme", "95");
        saved.sync();
        QTRY_COMPARE_WITH_TIMEOUT(manager.activeId(), QStringLiteral("95"), 2000);
        QTRY_COMPARE_WITH_TIMEOUT(guideAndNotificationManager.activeId(), QStringLiteral("95"), 2000);
    }
};

QTEST_GUILESS_MAIN(ThemeManagerTest)
#include "theme-manager-test.moc"
