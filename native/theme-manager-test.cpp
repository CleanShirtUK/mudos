#include "theme-manager.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QTemporaryDir>
#include <QUrl>
#include <QtTest>
#include <functional>
#include <limits>

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
        QVERIFY(copyTree(QStringLiteral(THEME_SOURCE_DIR) + "/metalheart", root + "/metalheart"));

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
            QJsonObject views = labels.value("views").toObject();
            views.insert("utilities", "Tools");
            views.insert("library", "Archive");
            labels.insert("views", views);
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
        QVERIFY(editTheme("bad-wallpaper-speed", [](QJsonObject &json) {
            QJsonObject motion = json.value("motion").toObject();
            QJsonObject roles = motion.value("roles").toObject();
            roles.insert("wallpaper", QJsonObject{{"enabled", true}, {"speed", 10.1}});
            motion.insert("roles", roles);
            json.insert("motion", motion);
        }));
        QVERIFY(editTheme("bad-radius-policy", [](QJsonObject &json) {
            json.insert("radiusPolicy", "theme-magic");
        }));
        auto invalidMaterial = [&](const QString &id, const std::function<void(QJsonObject &)> &edit) {
            return editTheme(id, [&](QJsonObject &json) {
                QJsonObject materials = json.value("materials").toObject();
                QJsonObject panel{{"style", "linearGradient"}, {"orientation", "vertical"},
                    {"stops", QJsonArray{QJsonObject{{"position", 0}, {"color", "#ffffff"}},
                                         QJsonObject{{"position", 1}, {"color", "#000000"}}}}};
                edit(panel);
                materials.insert("panel", panel);
                json.insert("materials", materials);
            });
        };
        QVERIFY(invalidMaterial("bad-material-style", [](QJsonObject &panel) { panel.insert("style", "radial"); }));
        QVERIFY(invalidMaterial("bad-material-orientation", [](QJsonObject &panel) { panel.insert("orientation", "diagonal"); }));
        QVERIFY(invalidMaterial("few-material-stops", [](QJsonObject &panel) { panel.insert("stops", QJsonArray{QJsonObject{{"position", 0}, {"color", "#fff"}}}); }));
        QVERIFY(invalidMaterial("many-material-stops", [](QJsonObject &panel) {
            QJsonArray stops; for (int i = 0; i < 9; ++i) stops.append(QJsonObject{{"position", i / 8.0}, {"color", "#ffffff"}});
            panel.insert("stops", stops);
        }));
        QVERIFY(invalidMaterial("unsorted-material-stops", [](QJsonObject &panel) {
            panel.insert("stops", QJsonArray{QJsonObject{{"position", 0.8}, {"color", "#ffffff"}},
                                              QJsonObject{{"position", 0.2}, {"color", "#000000"}}});
        }));
        QVERIFY(invalidMaterial("invalid-material-color", [](QJsonObject &panel) {
            panel.insert("stops", QJsonArray{QJsonObject{{"position", 0}, {"color", "nope"}},
                                              QJsonObject{{"position", 1}, {"color", "#000000"}}});
        }));
        QVERIFY(invalidMaterial("nan-material-position", [](QJsonObject &panel) {
            panel.insert("stops", QJsonArray{QJsonObject{{"position", QJsonValue(std::numeric_limits<double>::quiet_NaN())}, {"color", "#ffffff"}},
                                              QJsonObject{{"position", 1}, {"color", "#000000"}}});
        }));
        QVERIFY(invalidMaterial("bad-material-edge-width", [](QJsonObject &panel) {
            panel.insert("edges", QJsonObject{{"top", QJsonObject{{"color", "#ffffff"}, {"width", 8.1}}}});
        }));
        QVERIFY(editTheme("unknown-material-role", [](QJsonObject &json) {
            QJsonObject materials = json.value("materials").toObject();
            materials.insert("metalheartPanel", QJsonObject{{"style", "flat"}});
            json.insert("materials", materials);
        }));

        QVERIFY(editTheme("bad-decoration-slot", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"center", QJsonObject{{"asset", "icons/settings.svg"}}}}}});
        }));
        QVERIFY(editTheme("missing-decoration", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "decorations/missing.svg"}}}}}});
        }));
        QVERIFY(editTheme("traversal-decoration", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "../outside.svg"}}}}}});
        }));
        QVERIFY(editTheme("bad-decoration-tint", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "icons/settings.svg"}, {"tint", "theme-expression"}}}}}});
        }));
        QVERIFY(editTheme("bad-decoration-scale", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "icons/settings.svg"}, {"scale", 2.1}}}}}});
        }));
        QVERIFY(editTheme("bad-decoration-opacity", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "icons/settings.svg"}, {"opacity", -0.1}}}}}});
        }));
        QVERIFY(editTheme("unknown-decoration-role", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"metalheartPanel", QJsonObject{}}});
        }));
        QVERIFY(editTheme("decoration-coordinates", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "icons/settings.svg"}, {"x", 10}}}}}});
        }));
        QVERIFY(editTheme("bad-decoration-svg", [](QJsonObject &json) {
            json.insert("decorations", QJsonObject{{"panel", QJsonObject{{"topLeft", QJsonObject{{"asset", "icons/settings.svg"}}}}}});
        }));
        QVERIFY(QDir().mkpath(root + "/bad-decoration-svg/icons"));
        QFile badDecorationSvg(root + "/bad-decoration-svg/icons/settings.svg");
        QVERIFY(badDecorationSvg.open(QIODevice::WriteOnly | QIODevice::Truncate));
        badDecorationSvg.write("<svg><script>no</script></svg>");
        badDecorationSvg.close();
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
        QVERIFY(editTheme("bad-view-label", [](QJsonObject &json) {
            QJsonObject labels = json.value("labels").toObject();
            QJsonObject views = labels.value("views").toObject();
            views.insert("utilities", QString(65, QLatin1Char('x')));
            labels.insert("views", views);
            json.insert("labels", labels);
        }));
        QVERIFY(editTheme("bad-view-title", [](QJsonObject &json) {
            QJsonObject styles = json.value("textStyles").toObject();
            QJsonObject viewTitle = styles.value("viewTitle").toObject();
            viewTitle.insert("case", "execute");
            styles.insert("viewTitle", viewTitle);
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

        QVERIFY(copyTree(root + "/modern", root + "/decoration-escaped"));
        QFile escapedDecorationConfig(root + "/decoration-escaped/theme.json");
        QVERIFY(escapedDecorationConfig.open(QIODevice::ReadOnly));
        QJsonObject escapedDecorationJson = QJsonDocument::fromJson(escapedDecorationConfig.readAll()).object();
        escapedDecorationConfig.close();
        escapedDecorationJson.insert("id", "decoration-escaped");
        escapedDecorationJson.insert("decorations", QJsonObject{{"panel", QJsonObject{
            {"topLeft", QJsonObject{{"asset", "decorations/escape.svg"}}}}}});
        QVERIFY(escapedDecorationConfig.open(QIODevice::WriteOnly | QIODevice::Truncate));
        escapedDecorationConfig.write(QJsonDocument(escapedDecorationJson).toJson());
        escapedDecorationConfig.close();
        QVERIFY(QDir().mkpath(root + "/decoration-escaped/decorations"));
        QVERIFY(QFile::link(outsideSvg, root + "/decoration-escaped/decorations/escape.svg"));

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
        QCOMPARE(manager.labels().value("views").toMap().value("utilities").toString(), QStringLiteral("Utilities"));
        QCOMPARE(manager.labels().value("views").toMap().value("installable").toString(), QStringLiteral("Installable"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("case").toString(), QStringLiteral("upper"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("letterSpacing").toDouble(), 5.0);
        QCOMPARE(manager.textStyles().value("viewTitle").toMap().value("case").toString(), QStringLiteral("upper"));
        QCOMPARE(manager.textStyles().value("viewTitle").toMap().value("letterSpacing").toDouble(), 5.0);
        QCOMPARE(saved.value("appearance/theme").toString(), QStringLiteral("modern"));
        QStringList ids;
        for (const QVariant &theme : manager.themes()) ids.append(theme.toMap().value("id").toString());
        QCOMPARE(ids, QStringList({"modern", "95", "custom", "metalheart", "missing-motion"}));
        QVERIFY(!ids.contains("mudos-default"));
        QVERIFY(!ids.contains("invalid"));
        QVERIFY(!ids.contains("escaped"));
        QVERIFY(!ids.contains("bad-svg"));
        QVERIFY(!ids.contains("invalid-easing"));
        QVERIFY(!ids.contains("negative-duration"));
        QVERIFY(!ids.contains("bad-scale"));
        QVERIFY(!ids.contains("bad-wallpaper-speed"));
        QVERIFY(!ids.contains("bad-radius-policy"));
        for (const QString &invalidId : {"bad-material-style", "bad-material-orientation",
                 "few-material-stops", "many-material-stops", "unsorted-material-stops",
                 "invalid-material-color", "nan-material-position", "bad-material-edge-width",
                 "unknown-material-role", "bad-decoration-slot", "missing-decoration",
                 "traversal-decoration", "bad-decoration-tint", "bad-decoration-scale",
                 "bad-decoration-opacity", "unknown-decoration-role", "decoration-coordinates"})
            QVERIFY2(!ids.contains(invalidId), qPrintable(invalidId));
        QVERIFY(!ids.contains("bad-decoration-svg"));
        QVERIFY(!ids.contains("decoration-escaped"));
        QVERIFY(!ids.contains("zero-scale"));
        QVERIFY(!ids.contains("null-scale"));
        QVERIFY(!ids.contains("bad-label"));
        QVERIFY(!ids.contains("bad-case"));
        QVERIFY(!ids.contains("bad-spacing"));
        QVERIFY(!ids.contains("bad-view-label"));
        QVERIFY(!ids.contains("bad-view-title"));

        QVERIFY(manager.select("95"));
        QCOMPARE(manager.activeName(), QStringLiteral("95"));
        QCOMPARE(manager.motion().value("enabled").toBool(), false);
        QCOMPARE(manager.labels().value("home").toMap().value("recent").toString(), QStringLiteral("Recent"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("case").toString(), QStringLiteral("preserve"));
        QCOMPARE(manager.textStyles().value("homeTitle").toMap().value("letterSpacing").toDouble(), 0.0);
        QCOMPARE(manager.labels().value("views").toMap().value("utilities").toString(), QStringLiteral("Utilities"));
        QCOMPARE(manager.textStyles().value("viewTitle").toMap().value("case").toString(), QStringLiteral("preserve"));
        QCOMPARE(manager.textStyles().value("viewTitle").toMap().value("letterSpacing").toDouble(), 0.0);
        QCOMPARE(manager.glass().value("enabled").toBool(), false);
        QCOMPARE(manager.radii().value("panel").toDouble(), 0.0);
        QCOMPARE(manager.radiusPolicy(), QStringLiteral("exact"));
        QCOMPARE(manager.chrome().value("style").toString(), QStringLiteral("bevel"));
        QCOMPARE(manager.materials().size(), 0);
        QCOMPARE(manager.decorations().size(), 0);
        QVERIFY(manager.wallpaperShader().contains("themes/95/wallpaper/wallpaper.frag.qsb"));
        QVERIFY(manager.fonts().value("regular").toString().contains("themes/95/fonts/"));
        QVERIFY(manager.iconUrl("settings").contains("themes/95/icons/settings.svg"));
        QCOMPARE(saved.value("appearance/theme").toString(), QStringLiteral("95"));
        QVERIFY(manager.select("modern"));
        QCOMPARE(manager.colors().value("backdrop").toString(), QStringLiteral("#060607"));
        QCOMPARE(manager.radiusPolicy(), QStringLiteral("componentBaseline"));
        QCOMPARE(manager.chrome().value("style").toString(), QStringLiteral("flat"));
        QCOMPARE(manager.materials().size(), 0);
        QCOMPARE(manager.decorations().size(), 0);
        QVERIFY(manager.motion().value("roles").toMap().value("wallpaper").toMap()
                    .value("enabled").toBool());
        QCOMPARE(manager.motion().value("roles").toMap().value("wallpaper").toMap()
                     .value("speed").toDouble(), 1.0);
        QVERIFY(manager.select("metalheart"));
        QCOMPARE(manager.activeName(), QStringLiteral("Metalheart"));
        QCOMPARE(manager.colors().value("backdrop").toString(), QStringLiteral("#050508"));
        QCOMPARE(manager.radii().value("panel").toDouble(), 0.0);
        QCOMPARE(manager.radiusPolicy(), QStringLiteral("exact"));
        QCOMPARE(manager.chrome().value("style").toString(), QStringLiteral("flat"));
        QCOMPARE(manager.materials().size(), 6);
        const QVariantMap panelMaterial = manager.materials().value("panel").toMap();
        QCOMPARE(panelMaterial.value("style").toString(), QStringLiteral("linearGradient"));
        QCOMPARE(panelMaterial.value("orientation").toString(), QStringLiteral("vertical"));
        QCOMPARE(panelMaterial.value("stops").toList().size(), 7);
        QCOMPARE(panelMaterial.value("edges").toMap().value("top").toMap()
                     .value("width").toDouble(), 1.0);
        QCOMPARE(manager.materials().value("card").toMap().value("orientation").toString(),
                 QStringLiteral("vertical"));
        QCOMPARE(manager.materials().value("navigation").toMap().value("style").toString(),
                 QStringLiteral("linearGradient"));
        QCOMPARE(manager.materials().value("status").toMap().value("style").toString(),
                 QStringLiteral("linearGradient"));
        QCOMPARE(manager.materials().value("overlay").toMap().value("style").toString(),
                 QStringLiteral("linearGradient"));
        QCOMPARE(manager.materials().value("row").toMap().value("orientation").toString(),
                 QStringLiteral("horizontal"));
        QCOMPARE(manager.decorations().value("panel").toMap().value("topLeft").toMap()
                     .value("asset").toString().section('/', -2),
                 QStringLiteral("decorations/corner-bracket.svg"));
        QCOMPARE(manager.glass().value("enabled").toBool(), true);
        QCOMPARE(manager.glass().value("panel").toMap().value("transmission").toDouble(), 0.86);
        QCOMPARE(manager.motion().value("durationScale").toDouble(), 0.72);
        QCOMPARE(manager.motion().value("roles").toMap().value("surface").toMap()
                     .value("duration").toInt(), 340);
        QVERIFY(manager.motion().value("roles").toMap().value("wallpaper").toMap()
                    .value("enabled").toBool());
        QCOMPARE(manager.motion().value("roles").toMap().value("wallpaper").toMap()
                     .value("speed").toDouble(), 1.0);
        QCOMPARE(manager.labels().value("home").toMap().value("store").toString(), QStringLiteral("ACQUIRE"));
        QCOMPARE(manager.fonts().value("regular").toString().contains("themes/metalheart/fonts/ShareTechMono-Regular.ttf"), true);
        QCOMPARE(manager.fonts().value("heavy").toString().contains("themes/metalheart/fonts/Oxanium-Variable.ttf"), true);
        QVERIFY(manager.wallpaperShader().contains("themes/metalheart/wallpaper/wallpaper.frag.qsb"));
        QVERIFY(manager.iconUrl("settings").contains("themes/metalheart/icons/settings.svg"));
        QVERIFY(manager.select("missing-motion"));
        QCOMPARE(manager.motion().value("enabled").toBool(), true);
        QCOMPARE(manager.motion().value("durationScale").toDouble(), 1.0);
        QVERIFY(manager.select("custom"));
        QCOMPARE(manager.labels().value("home").toMap().value("recent").toString(), QStringLiteral("Last Played"));
        QCOMPARE(manager.labels().value("views").toMap().value("utilities").toString(), QStringLiteral("Tools"));
        QCOMPARE(manager.labels().value("views").toMap().value("library").toString(), QStringLiteral("Archive"));
        QVERIFY(manager.select("modern"));
        ThemeManager guideAndNotificationManager;
        QCOMPARE(guideAndNotificationManager.activeId(), QStringLiteral("modern"));
        saved.setValue("appearance/theme", "95");
        saved.sync();
        QTRY_COMPARE_WITH_TIMEOUT(manager.activeId(), QStringLiteral("95"), 2000);
        QTRY_COMPARE_WITH_TIMEOUT(guideAndNotificationManager.activeId(), QStringLiteral("95"), 2000);
    }

    void pngSemanticIconsAndTextRolesAreValidatedAndResolved()
    {
        QTemporaryDir temp;
        QVERIFY(temp.isValid());
        const QString root = QDir(temp.path()).filePath("themes");
        for (const QString &id : {"modern", "95", "metalheart", "frutiger-aero"})
            QVERIFY(copyTree(QStringLiteral(THEME_SOURCE_DIR) + "/" + id, root + "/" + id));
        QVERIFY(copyTree(root + "/frutiger-aero", root + "/candidate"));
        QVERIFY(QDir().mkpath(root + "/candidate/icons"));

        const QString candidateConfigPath = root + "/candidate/theme.json";
        auto readObject = [](const QString &path) {
            QFile file(path);
            if (!file.open(QIODevice::ReadOnly)) return QJsonObject{};
            return QJsonDocument::fromJson(file.readAll()).object();
        };
        auto writeObject = [](const QString &path, const QJsonObject &object) {
            QFile file(path);
            if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
            return file.write(QJsonDocument(object).toJson()) >= 0;
        };
        auto candidateWith = [&](const QString &relative, const QString &render,
                                 const std::function<void(const QString &)> &writeAsset) {
            QJsonObject config = readObject(candidateConfigPath);
            config.insert("id", "candidate");
            QJsonObject icons = config.value("icons").toObject();
            icons.insert("settings", QJsonObject{{"file", relative}, {"render", render}});
            config.insert("icons", icons);
            if (!writeObject(candidateConfigPath, config)) return false;
            writeAsset(QDir(root + "/candidate").filePath(relative));
            return true;
        };
        auto candidateIsExcluded = [&]() {
            ThemeManager manager;
            for (const QVariant &entry : manager.themes())
                if (entry.toMap().value("id").toString() == "candidate") return false;
            return true;
        };
        qputenv("MUDOS_THEME_ROOTS", root.toUtf8());
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope,
                           QDir(temp.path()).filePath("settings"));
        QSettings saved(QSettings::IniFormat, QSettings::UserScope, "Mudos", "lulu");
        saved.setValue("appearance/theme", "modern");
        saved.sync();

        {
            ThemeManager manager;
            QStringList ids;
            for (const QVariant &entry : manager.themes())
                ids.append(entry.toMap().value("id").toString());
            QVERIFY(ids.contains("frutiger-aero"));
            QVERIFY(ids.indexOf("modern") < ids.indexOf("95"));
            QVERIFY(manager.select("frutiger-aero"));
            QCOMPARE(manager.activeName(), QStringLiteral("Frutiger Aero"));
            const QVariantMap png = manager.iconAsset("settings");
            QCOMPARE(png.value("format").toString(), QStringLiteral("png"));
            QCOMPARE(png.value("renderMode").toString(), QStringLiteral("original"));
            QVERIFY(png.value("url").toString().contains("frutiger-aero/icons/settings.png"));
            QCOMPARE(manager.iconUrl("settings"), png.value("url").toString());
            const QVariantMap styles = manager.textStyles();
            for (const QString &role : {"heading", "body", "metadata", "annotation", "status"})
                QVERIFY2(styles.contains(role), qPrintable(role));
            QCOMPARE(styles.value("heading").toMap().value("fontRole").toString(),
                     QStringLiteral("majorHeading"));
            QCOMPARE(styles.value("metadata").toMap().value("letterSpacing").toDouble(), 0.1);
            QVERIFY(manager.select("modern"));
            QVERIFY(manager.iconAsset("settings").isEmpty());
            QVERIFY(manager.select("metalheart"));
            QCOMPARE(manager.iconAsset("settings").value("format").toString(), QStringLiteral("svg"));
            QCOMPARE(manager.iconAsset("settings").value("renderMode").toString(), QStringLiteral("tint"));
        }

        auto writePng = [](const QString &path, const QSize &size) {
            QDir().mkpath(QFileInfo(path).absolutePath());
            QImage image(size, QImage::Format_RGBA8888);
            image.fill(QColor(20, 150, 230, 180));
            return image.save(path, "PNG");
        };
        QVERIFY(candidateWith("icons/test.png", "original", [&](const QString &path) {
            QVERIFY(writePng(path, QSize(80, 40)));
        }));
        QVERIFY(!candidateIsExcluded());

        QVERIFY(candidateWith("icons/test.png", "original", [](const QString &path) {
            QFile file(path); QDir().mkpath(QFileInfo(path).absolutePath());
            if (file.open(QIODevice::WriteOnly)) file.write("not a PNG");
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("icons/test.png", "original", [](const QString &path) {
            QFile file(path); QDir().mkpath(QFileInfo(path).absolutePath());
            if (file.open(QIODevice::WriteOnly)) file.write(QByteArray::fromHex("89504e470d0a1a0a") + "corrupt-data");
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("icons/test.png", "original", [&](const QString &path) {
            QVERIFY(writePng(path, QSize(1025, 1)));
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("icons/test.png", "original", [](const QString &path) {
            QDir().mkpath(QFileInfo(path).absolutePath());
            QFile file(path);
            if (file.open(QIODevice::WriteOnly)) {
                QByteArray bytes = QByteArray::fromHex("89504e470d0a1a0a");
                bytes += QByteArray(4 * 1024 * 1024, 'x');
                file.write(bytes);
            }
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("../outside.png", "original", [](const QString &) {}));
        QVERIFY(candidateIsExcluded());

        const QString outsidePng = QDir(temp.path()).filePath("outside.png");
        QVERIFY(writePng(outsidePng, QSize(8, 8)));
        QVERIFY(candidateWith("icons/test.png", "original", [&](const QString &path) {
            QFile::remove(path);
            QFile::link(outsidePng, path);
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("icons/settings.svg", "original", [&](const QString &path) {
            QFile::remove(path);
            QVERIFY(QFile::copy(QStringLiteral(THEME_SOURCE_DIR)
                                    + "/metalheart/icons/settings.svg", path));
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("icons/test.png", "tint", [&](const QString &path) {
            QVERIFY(writePng(path, QSize(8, 8)));
        }));
        QVERIFY(candidateIsExcluded());

        QVERIFY(candidateWith("icons/settings.svg", "tint", [&](const QString &path) {
            QFile::remove(path);
            QVERIFY(QFile::copy(QStringLiteral(THEME_SOURCE_DIR)
                                    + "/metalheart/icons/settings.svg", path));
        }));
        QVERIFY(!candidateIsExcluded());

        auto invalidTextRole = [&](const QString &id, const QString &field,
                                   const QJsonValue &value) {
            QJsonObject config = readObject(candidateConfigPath);
            config.insert("id", id);
            QJsonObject textStyles = config.value("textStyles").toObject();
            QJsonObject heading = textStyles.value("heading").toObject();
            heading.insert(field, value);
            textStyles.insert("heading", heading);
            config.insert("textStyles", textStyles);
            return writeObject(candidateConfigPath, config);
        };
        for (const auto &bad : {qMakePair(QStringLiteral("bad-text-font"), QPair<QString,QJsonValue>{"fontRole", "runtime"}),
                                qMakePair(QStringLiteral("bad-text-weight"), QPair<QString,QJsonValue>{"weight", 1001}),
                                qMakePair(QStringLiteral("bad-text-case"), QPair<QString,QJsonValue>{"case", "titleCase"}),
                                qMakePair(QStringLiteral("bad-text-spacing"), QPair<QString,QJsonValue>{"letterSpacing", 33}),
                                qMakePair(QStringLiteral("theme-text-size"), QPair<QString,QJsonValue>{"pixelSize", 20})}) {
            QVERIFY(invalidTextRole(bad.first, bad.second.first, bad.second.second));
            QVERIFY(candidateIsExcluded());
        }
    }
};

QTEST_GUILESS_MAIN(ThemeManagerTest)
#include "theme-manager-test.moc"
