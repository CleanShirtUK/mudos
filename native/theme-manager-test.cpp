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
#include <functional>

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

        auto editTheme = [&](const QString &id, const std::function<void(QJsonObject &)> &edit) {
            const QString dir = root + "/" + id;
            if (!copyTree(root + "/modern", dir)) return false;
            QFile config(dir + "/theme.json");
            if (!config.open(QIODevice::ReadOnly)) return false;
            QJsonObject json = QJsonDocument::fromJson(config.readAll()).object();
            config.close();
            json.insert("id", id);
            edit(json);
            if (!config.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
            config.write(QJsonDocument(json).toJson());
            return true;
        };
        QVERIFY(editTheme("custom", [](QJsonObject &json) {
            QJsonObject labels = json.value("labels").toObject();
            QJsonObject home = labels.value("home").toObject();
            home.insert("recent", "Last Played");
            labels.insert("home", home);
            json.insert("labels", labels);
        }));
        QVERIFY(editTheme("missing-motion", [](QJsonObject &json) {
            json.remove("motion");
        }));
        QVERIFY(editTheme("invalid-easing", [](QJsonObject &json) {
            QJsonObject motion = json.value("motion").toObject();
            QJsonObject roles = motion.value("roles").toObject();
            QJsonObject navigation = roles.value("navigation").toObject();
            navigation.insert("easing", "runJavaScript");
            roles.insert("navigation", navigation);
            motion.insert("roles", roles);
            json.insert("motion", motion);
        }));
        QVERIFY(editTheme("negative-duration", [](QJsonObject &json) {
            QJsonObject motion = json.value("motion").toObject();
            QJsonObject roles = motion.value("roles").toObject();
            QJsonObject navigation = roles.value("navigation").toObject();
            navigation.insert("duration", -1);
            roles.insert("navigation", navigation);
            motion.insert("roles", roles);
            json.insert("motion", motion);
        }));
        QVERIFY(editTheme("bad-scale", [](QJsonObject &json) {
            QJsonObject motion = json.value("motion").toObject();
            motion.insert("durationScale", 1e300);
            json.insert("motion", motion);
        }));
        QVERIFY(editTheme("zero-scale", [](QJsonObject &json) {
            QJsonObject motion = json.value("motion").toObject();
            motion.insert("durationScale", 0);
            json.insert("motion", motion);
        }));
        QVERIFY(editTheme("null-scale", [](QJsonObject &json) {
            QJsonObject motion = json.value("motion").toObject();
            motion.insert("durationScale", QJsonValue::Null);
            json.insert("motion", motion);
        }));
        QVERIFY(editTheme("bad-label", [](QJsonObject &json) {
            QJsonObject labels = json.value("labels").toObject();
            QJsonObject home = labels.value("home").toObject();
            home.insert("recent", QString(65, QLatin1Char('x')));
            labels.insert("home", home);
            json.insert("labels", labels);
        }));
        QVERIFY(editTheme("bad-case", [](QJsonObject &json) {
            QJsonObject styles = json.value("textStyles").toObject();
            QJsonObject homeTitle = styles.value("homeTitle").toObject();
            homeTitle.insert("case", "randomCode");
            styles.insert("homeTitle", homeTitle);
            json.insert("textStyles", styles);
        }));
        QVERIFY(editTheme("bad-spacing", [](QJsonObject &json) {
            QJsonObject styles = json.value("textStyles").toObject();
            QJsonObject homeTitle = styles.value("homeTitle").toObject();
            homeTitle.insert("letterSpacing", -1);
            styles.insert("homeTitle", homeTitle);
            json.insert("textStyles", styles);
        }));

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
        QCOMPARE(manager.motion().value("enabled").toBool(), true);
        QCOMPARE(manager.motion().value("roles").toMap().value("navigation").toMap().value("duration").toInt(), 250);
        QCOMPARE(manager.labels().value("home").toMap().value("recent").toString(), QStringLiteral("Recent"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("case").toString(), QStringLiteral("upper"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("letterSpacing").toDouble(), 5.0);
        QCOMPARE(saved.value("appearance/theme").toString(), QStringLiteral("modern"));
        QStringList ids;
        for (const QVariant &theme : manager.themes()) ids.append(theme.toMap().value("id").toString());
        QCOMPARE(ids, QStringList({"modern", "95", "custom", "missing-motion"}));
        QVERIFY(!ids.contains("mudos-default"));
        QVERIFY(!ids.contains("invalid"));
        QVERIFY(!ids.contains("escaped"));
        QVERIFY(!ids.contains("bad-svg"));
        QVERIFY(!ids.contains("invalid-easing"));
        QVERIFY(!ids.contains("negative-duration"));
        QVERIFY(!ids.contains("bad-scale"));
        QVERIFY(!ids.contains("zero-scale"));
        QVERIFY(!ids.contains("null-scale"));
        QVERIFY(!ids.contains("bad-label"));
        QVERIFY(!ids.contains("bad-case"));
        QVERIFY(!ids.contains("bad-spacing"));

        QVERIFY(manager.select("95"));
        QCOMPARE(manager.activeName(), QStringLiteral("95"));
        QCOMPARE(manager.motion().value("enabled").toBool(), false);
        QCOMPARE(manager.labels().value("home").toMap().value("recent").toString(), QStringLiteral("Recent"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("case").toString(), QStringLiteral("preserve"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("letterSpacing").toDouble(), 0.0);
        QCOMPARE(manager.glass().value("enabled").toBool(), false);
        QCOMPARE(manager.radii().value("panel").toDouble(), 0.0);
        QVERIFY(manager.wallpaperShader().contains("themes/95/wallpaper/wallpaper.frag.qsb"));
        QVERIFY(manager.fonts().value("regular").toString().contains("themes/95/fonts/"));
        QVERIFY(manager.iconUrl("settings").contains("themes/95/icons/settings.svg"));
        QCOMPARE(saved.value("appearance/theme").toString(), QStringLiteral("95"));
        QVERIFY(manager.select("modern"));
        QCOMPARE(manager.colors().value("backdrop").toString(), QStringLiteral("#060607"));
        QVERIFY(manager.select("missing-motion"));
        QCOMPARE(manager.motion().value("enabled").toBool(), true);
        QCOMPARE(manager.motion().value("durationScale").toDouble(), 1.0);
        QVERIFY(manager.select("custom"));
        QCOMPARE(manager.labels().value("home").toMap().value("recent").toString(), QStringLiteral("Last Played"));
        QVERIFY(manager.select("modern"));
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
