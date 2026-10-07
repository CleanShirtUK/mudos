#include "theme-manager.h"

#include <QColor>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QSet>
#include <QStandardPaths>
#include <QTimer>
#include <QXmlStreamReader>
#include <QtEndian>
#include <QUrl>
#include <algorithm>
#include <cmath>

namespace {
bool validSvg(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 512 * 1024) return false;
    QXmlStreamReader xml(&file);
    bool sawRoot = false;
    while (!xml.atEnd()) {
        xml.readNext();
        if (xml.isDTD()) return false;
        if (xml.isStartElement()) {
            if (!sawRoot) {
                if (xml.name() != QLatin1String("svg")) return false;
                sawRoot = true;
            }
            if (xml.name() == QLatin1String("script")
                || xml.name() == QLatin1String("foreignObject")) return false;
            for (const auto &attribute : xml.attributes())
                if (attribute.name() == QLatin1String("href")) return false;
        }
    }
    return sawRoot && !xml.hasError();
}

bool validQsb(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 32 * 1024 * 1024) return false;
    const QByteArray serialized = file.readAll();
    if (serialized.size() < 8) return false;
    const quint32 expectedSize = qFromBigEndian<quint32>(
        reinterpret_cast<const uchar *>(serialized.constData()));
    if (expectedSize == 0 || expectedSize > 64 * 1024 * 1024) return false;
    const QByteArray payload = qUncompress(serialized);
    return !payload.isEmpty()
        && static_cast<quint32>(payload.size()) == expectedSize;
}

QString contained(const QString &base, const QString &relative)
{
    if (relative.isEmpty() || QDir::isAbsolutePath(relative) || relative.contains("://")) return {};
    const QString canonicalBase = QFileInfo(base).canonicalFilePath();
    const QString canonicalFile = QFileInfo(QDir(base).filePath(relative)).canonicalFilePath();
    if (canonicalBase.isEmpty() || canonicalFile.isEmpty()
        || !(canonicalFile == canonicalBase || canonicalFile.startsWith(canonicalBase + QDir::separator()))) return {};
    return canonicalFile;
}
}

ThemeManager::ThemeManager(QObject *parent) : QObject(parent)
{
    // Discover and activate through the same complete validator. Discovery
    // must never advertise a theme that select() cannot load.
    for (const QString &base : roots()) {
        QDir dir(base);
        for (const QString &entry : dir.entryList(QDir::Dirs | QDir::NoDotAndDotDot)) {
            if (entry == "mudos-default") continue; // compatibility alias, not a theme
            QVariantMap validated;
            if (!inspectAt(QDir(base).filePath(entry), entry, &validated)) continue;
            bool duplicate = false;
            for (const QVariant &theme : m_themes)
                if (theme.toMap().value("id").toString() == entry) duplicate = true;
            if (!duplicate)
                m_themes.append(QVariantMap{{"id", entry}, {"name", validated.value("name")}});
        }
    }
    std::stable_sort(m_themes.begin(), m_themes.end(), [](const QVariant &a, const QVariant &b) {
        const QString left = a.toMap().value("id").toString();
        const QString right = b.toMap().value("id").toString();
        if (left == "modern") return right != "modern";
        if (right == "modern") return false;
        if (left == "95") return right != "95";
        if (right == "95") return false;
        return left < right;
    });
    emit themesChanged();
    load(QString(), false);
    watchSettings();
}

void ThemeManager::watchSettings()
{
    QSettings settings(QSettings::IniFormat, QSettings::UserScope, "Mudos", "lulu");
    const QString fileName = settings.fileName();
    const QString directory = QFileInfo(fileName).absolutePath();
    m_settingsWatcher = new QFileSystemWatcher(this);
    m_settingsReload = new QTimer(this);
    m_settingsReload->setSingleShot(true);
    m_settingsReload->setInterval(80);
    connect(m_settingsReload, &QTimer::timeout, this, [this, fileName, directory]() {
        if (QFileInfo::exists(fileName) && !m_settingsWatcher->files().contains(fileName))
            m_settingsWatcher->addPath(fileName);
        if (!m_settingsWatcher->directories().contains(directory))
            m_settingsWatcher->addPath(directory);
        load(QString(), false);
    });
    connect(m_settingsWatcher, &QFileSystemWatcher::fileChanged,
            m_settingsReload, qOverload<>(&QTimer::start));
    connect(m_settingsWatcher, &QFileSystemWatcher::directoryChanged,
            m_settingsReload, qOverload<>(&QTimer::start));
    if (QFileInfo::exists(fileName)) m_settingsWatcher->addPath(fileName);
    if (QFileInfo::exists(directory)) m_settingsWatcher->addPath(directory);
}

QStringList ThemeManager::roots() const
{
    QStringList result;
    const QString override = qEnvironmentVariable("MUDOS_THEME_ROOTS");
    if (!override.isEmpty()) result.append(override.split(QLatin1Char(':'), Qt::SkipEmptyParts));
    else {
        result << QDir(qEnvironmentVariable("LULU_INSTALL_ROOT", "/opt/lulu")).filePath("themes");
        QString data = qEnvironmentVariable("XDG_DATA_HOME");
        if (data.isEmpty()) data = QDir::home().filePath(".local/share");
        result << QDir(data).filePath("mudos/themes");
    }
    return result;
}

bool ThemeManager::load(const QString &requested, bool persist)
{
    QString id = requested;
    if (id.isEmpty()) {
        QSettings settings(QSettings::IniFormat, QSettings::UserScope, "Mudos", "lulu");
        id = settings.value("appearance/theme", "modern").toString();
    }
    const bool legacyAlias = id == "mudos-default";
    if (legacyAlias) id = "modern";
    for (const QString &base : roots()) {
        QVariantMap validated;
        if (inspectAt(QDir(base).filePath(id), id, &validated)) return apply(validated, persist || legacyAlias);
    }
    if (id != "modern") {
        qWarning() << "Theme invalid or unavailable; falling back to modern:" << id;
        for (const QString &base : roots()) {
            QVariantMap validated;
            if (inspectAt(QDir(base).filePath("modern"), "modern", &validated)) return apply(validated, true);
        }
    }
    return false;
}

bool ThemeManager::inspectAt(const QString &directory, const QString &expectedId,
                             QVariantMap *resolved) const
{
    if (!resolved || expectedId.isEmpty() || expectedId == "mudos-default") return false;
    const QString configPath = contained(directory, "theme.json");
    QFile config(configPath);
    if (configPath.isEmpty() || !config.open(QIODevice::ReadOnly)) return false;
    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(config.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject()) return false;
    const QJsonObject data = doc.object();
    if (data.value("schema_version").toInt() != 1 || data.value("id").toString() != expectedId) return false;
    if (data.value("name").toString().trimmed().isEmpty()) return false;
    const QJsonObject c = data.value("colors").toObject();
    const QJsonObject o = data.value("opacity").toObject();
    const QJsonObject r = data.value("radii").toObject();
    if (data.contains("radiusPolicy") && !data.value("radiusPolicy").isString()) return false;
    const QString radiusPolicy = data.value("radiusPolicy").toString("componentBaseline");
    if (radiusPolicy != QLatin1String("exact")
        && radiusPolicy != QLatin1String("componentBaseline")) return false;
    const QJsonObject g = data.value("glass").toObject();
    const QJsonObject chrome = data.value("chrome").toObject();
    const QJsonObject f = data.value("fonts").toObject();
    const QJsonObject faces = f.value("faces").toObject();
    const QJsonObject icons = data.value("icons").toObject();
    if (data.contains("materials") && !data.value("materials").isObject()) return false;
    if (data.contains("decorations") && !data.value("decorations").isObject()) return false;
    const QJsonObject materials = data.value("materials").toObject();
    const QJsonObject decorations = data.value("decorations").toObject();
    QJsonObject motion = data.value("motion").toObject();
    if (data.contains("motion") && !data.value("motion").isObject()) return false;
    if (motion.isEmpty()) motion = QJsonObject{{"enabled", true}, {"durationScale", 1.0}};
    if (motion.contains("roles") && !motion.value("roles").isObject()) return false;
    const QJsonObject motionRoles = motion.value("roles").toObject();
    if (!motion.value("enabled").isBool()) return false;
    const QJsonValue scaleValue = motion.value("durationScale");
    if (!scaleValue.isDouble() || !std::isfinite(scaleValue.toDouble())
        || scaleValue.toDouble() <= 0 || scaleValue.toDouble() > 10) return false;
    const QSet<QString> easings{"linear", "inCubic", "outCubic", "inOutCubic",
        "inQuint", "outQuint", "inOutQuint", "inQuad", "outQuad", "inOutQuad"};
    for (auto it = motionRoles.begin(); it != motionRoles.end(); ++it) {
        if (!it.value().isObject()) return false;
        const QJsonObject role = it.value().toObject();
        if (role.contains("enabled") && !role.value("enabled").isBool()) return false;
        if (role.contains("duration") && (!role.value("duration").isDouble()
            || !std::isfinite(role.value("duration").toDouble())
            || role.value("duration").toDouble() < 0 || role.value("duration").toDouble() > 5000)) return false;
        if (role.contains("easing") && (!role.value("easing").isString()
            || !easings.contains(role.value("easing").toString()))) return false;
        if (role.contains("speed") && (!role.value("speed").isDouble()
            || !std::isfinite(role.value("speed").toDouble())
            || role.value("speed").toDouble() < 0
            || role.value("speed").toDouble() > 10)) return false;
    }
    const QJsonObject labels = data.value("labels").toObject();
    if (data.contains("labels") && !data.value("labels").isObject()) return false;
    QJsonObject homeLabels = labels.value("home").toObject();
    if (labels.contains("home") && !labels.value("home").isObject()) return false;
    const QMap<QString, QString> canonicalLabels{{"system", "System"}, {"store", "Store"},
        {"library", "Library"}, {"recent", "Recent"}};
    for (auto it = canonicalLabels.cbegin(); it != canonicalLabels.cend(); ++it) {
        if (!homeLabels.contains(it.key())) homeLabels.insert(it.key(), it.value());
        const QJsonValue label = homeLabels.value(it.key());
        if (!label.isString() || label.toString().trimmed().isEmpty() || label.toString().size() > 64) return false;
    }
    for (auto it = homeLabels.begin(); it != homeLabels.end(); ++it)
        if (!it.value().isString() || it.value().toString().trimmed().isEmpty()
            || it.value().toString().size() > 64) return false;
    QJsonObject viewLabels = labels.value("views").toObject();
    if (labels.contains("views") && !labels.value("views").isObject()) return false;
    const QMap<QString, QString> canonicalViews{{"settings", "Settings"},
        {"utilities", "Utilities"}, {"library", "Library"},
        {"installable", "Installable"}, {"downloads", "Downloads"}};
    for (auto it = canonicalViews.cbegin(); it != canonicalViews.cend(); ++it) {
        if (!viewLabels.contains(it.key())) viewLabels.insert(it.key(), it.value());
        const QJsonValue label = viewLabels.value(it.key());
        if (!label.isString() || label.toString().trimmed().isEmpty()
            || label.toString().size() > 64) return false;
    }
    for (auto it = viewLabels.begin(); it != viewLabels.end(); ++it)
        if (!it.value().isString() || it.value().toString().trimmed().isEmpty()
            || it.value().toString().size() > 64) return false;
    const QJsonObject textStyles = data.value("textStyles").toObject();
    if (data.contains("textStyles") && !data.value("textStyles").isObject()) return false;
    QJsonObject homeTitle = textStyles.value("homeTitle").toObject();
    if (textStyles.contains("homeTitle") && !textStyles.value("homeTitle").isObject()) return false;
    if (!homeTitle.contains("case")) homeTitle.insert("case", "preserve");
    if (!homeTitle.contains("letterSpacing")) homeTitle.insert("letterSpacing", 0);
    const QString titleCase = homeTitle.value("case").toString();
    const QJsonValue spacing = homeTitle.value("letterSpacing");
    if (titleCase != "preserve" && titleCase != "upper" && titleCase != "lower") return false;
    if (!spacing.isDouble() || !std::isfinite(spacing.toDouble()) || spacing.toDouble() < 0 || spacing.toDouble() > 32) return false;
    QJsonObject viewTitle = textStyles.value("viewTitle").toObject();
    if (textStyles.contains("viewTitle") && !textStyles.value("viewTitle").isObject()) return false;
    if (!viewTitle.contains("case")) viewTitle.insert("case", "preserve");
    if (!viewTitle.contains("letterSpacing")) viewTitle.insert("letterSpacing", 0);
    const QString viewTitleCase = viewTitle.value("case").toString();
    const QJsonValue viewTitleSpacing = viewTitle.value("letterSpacing");
    if (viewTitleCase != "preserve" && viewTitleCase != "upper"
        && viewTitleCase != "lower") return false;
    if (!viewTitleSpacing.isDouble() || !std::isfinite(viewTitleSpacing.toDouble())
        || viewTitleSpacing.toDouble() < 0 || viewTitleSpacing.toDouble() > 32) return false;
    auto requiredColor = [&](const char *key) {
        const QString value = c.value(QLatin1String(key)).toString();
        return value.startsWith(QLatin1Char('#')) && QColor(value).isValid();
    };
    for (const char *key : {"primaryText", "secondaryText", "mutedText", "selectedText", "accent", "focusIndicator", "warning", "backdrop", "surface", "surfaceElevated", "surfaceInternal", "cardSurface", "focusedCardSurface", "actionSurface", "actionText", "artworkSurface", "border", "focusBorder", "overlayBackdrop", "overlaySurface", "launchOverlaySurface", "guideSurface", "guideBorder", "guideItemSurface", "guideSelectedText", "scrollFadeStart", "scrollFadeEnd", "navigationText", "headingAccent", "selectionSurface", "librarySurface", "libraryCardSurface", "libraryBorder", "overlay"})
        if (!requiredColor(key)) return false;

    auto asset = [&](const QString &path) { return contained(directory, path); };
    QVariantMap fontPaths;
    for (const char *key : {"regular", "bold", "heavy", "icons", "controller"}) {
        const QJsonValue faceValue = faces.value(QLatin1String(key));
        if (!faceValue.isObject()) return false;
        const QString path = asset(faceValue.toObject().value("file").toString());
        if (path.isEmpty() || !QFileInfo(path).isFile()) return false;
        fontPaths.insert(QLatin1String(key), QUrl::fromLocalFile(path).toString());
    }
    for (auto it = faces.begin(); it != faces.end(); ++it) {
        const QString path = asset(it.value().toObject().value("file").toString());
        if (path.isEmpty() || !QFileInfo(path).isFile()) return false;
        fontPaths.insert(it.key(), QUrl::fromLocalFile(path).toString());
    }
    const QJsonObject roleMap = f.value("roles").toObject();
    for (const char *role : {"interface", "display", "majorHeading", "icon", "controller"}) {
        const QString face = roleMap.value(QLatin1String(role)).toString();
        if (face.isEmpty() || !faces.contains(face)) return false;
    }
    const QString wallpaper = asset(data.value("wallpaper").toObject().value("shader").toString());
    if (wallpaper.isEmpty() || !QFileInfo(wallpaper).isFile()
        || !wallpaper.endsWith(".qsb") || !validQsb(wallpaper)) return false;
    const QJsonObject wallpaperObject = data.value("wallpaper").toObject();
    for (const char *key : {"primary", "secondary", "surface", "error"}) {
        const QString value = wallpaperObject.value(QLatin1String(key)).toString();
        if (!value.startsWith('#') || !QColor(value).isValid()) return false;
    }
    QVariantMap iconPaths;
    for (auto it = icons.begin(); it != icons.end(); ++it) {
        const QString path = asset(it.value().toString());
        if (path.isEmpty() || !QFileInfo(path).isFile()
            || !it.value().toString().endsWith(".svg", Qt::CaseInsensitive)
            || !validSvg(path)) return false;
        iconPaths.insert(it.key(), QUrl::fromLocalFile(path).toString());
    }
    const QSet<QString> materialRoles{"panel", "card", "navigation", "status", "overlay", "row"};
    const QSet<QString> materialFields{"style", "orientation", "stops", "edges", "innerEdges"};
    const QSet<QString> edgeNames{"top", "bottom", "left", "right"};
    auto onlyKeys = [](const QJsonObject &object, const QSet<QString> &allowed) {
        for (auto it = object.begin(); it != object.end(); ++it)
            if (!allowed.contains(it.key())) return false;
        return true;
    };
    auto validateEdges = [&](const QJsonValue &value, QVariantMap *resolvedEdges) {
        if (!value.isObject()) return false;
        const QJsonObject edges = value.toObject();
        if (!onlyKeys(edges, edgeNames)) return false;
        for (auto it = edges.begin(); it != edges.end(); ++it) {
            if (!it.value().isObject()) return false;
            const QJsonObject edge = it.value().toObject();
            if (!onlyKeys(edge, QSet<QString>{"color", "width"})
                || edge.size() != 2) return false;
            const QJsonValue colorValue = edge.value("color");
            const QJsonValue widthValue = edge.value("width");
            if (!colorValue.isString() || !QColor(colorValue.toString()).isValid()
                || !widthValue.isDouble() || !std::isfinite(widthValue.toDouble())
                || widthValue.toDouble() < 0 || widthValue.toDouble() > 8) return false;
        }
        if (resolvedEdges) *resolvedEdges = edges.toVariantMap();
        return true;
    };
    QVariantMap resolvedMaterials;
    for (auto it = materials.begin(); it != materials.end(); ++it) {
        if (!materialRoles.contains(it.key()) || !it.value().isObject()) return false;
        const QJsonObject material = it.value().toObject();
        if (!onlyKeys(material, materialFields)) return false;
        const QString style = material.value("style").toString();
        if (style == QLatin1String("flat")) {
            if (material.contains("orientation") || material.contains("stops")) return false;
            QVariantMap resolved = material.toVariantMap();
            if (material.contains("edges")) {
                QVariantMap validated;
                if (!validateEdges(material.value("edges"), &validated)) return false;
                resolved.insert("edges", validated);
            }
            if (material.contains("innerEdges")) {
                QVariantMap validated;
                if (!validateEdges(material.value("innerEdges"), &validated)) return false;
                resolved.insert("innerEdges", validated);
            }
            resolvedMaterials.insert(it.key(), resolved);
            continue;
        }
        if (style != QLatin1String("linearGradient")
            || material.value("orientation").toString().isEmpty()
            || (material.value("orientation").toString() != QLatin1String("vertical")
                && material.value("orientation").toString() != QLatin1String("horizontal")))
            return false;
        const QJsonValue stopsValue = material.value("stops");
        if (!stopsValue.isArray()) return false;
        const QJsonArray stops = stopsValue.toArray();
        if (stops.size() < 2 || stops.size() > 8) return false;
        double previousPosition = -1.0;
        for (const QJsonValue &stopValue : stops) {
            if (!stopValue.isObject()) return false;
            const QJsonObject stop = stopValue.toObject();
            if (!onlyKeys(stop, QSet<QString>{"position", "color"}) || stop.size() != 2)
                return false;
            const QJsonValue position = stop.value("position");
            const QJsonValue colorValue = stop.value("color");
            if (!position.isDouble() || !std::isfinite(position.toDouble())
                || position.toDouble() < 0 || position.toDouble() > 1
                || position.toDouble() < previousPosition
                || !colorValue.isString() || !QColor(colorValue.toString()).isValid())
                return false;
            previousPosition = position.toDouble();
        }
        QVariantMap resolved = material.toVariantMap();
        if (material.contains("edges")) {
            QVariantMap validated;
            if (!validateEdges(material.value("edges"), &validated)) return false;
            resolved.insert("edges", validated);
        }
        if (material.contains("innerEdges")) {
            QVariantMap validated;
            if (!validateEdges(material.value("innerEdges"), &validated)) return false;
            resolved.insert("innerEdges", validated);
        }
        resolvedMaterials.insert(it.key(), resolved);
    }
    const QSet<QString> decorationRoles{"panel", "card", "status", "overlay"};
    const QSet<QString> decorationSlots{"topLeft", "topRight", "bottomLeft", "bottomRight"};
    const QSet<QString> tintRoles{"accent", "secondaryText", "border", "focusIndicator"};
    QVariantMap resolvedDecorations;
    for (auto it = decorations.begin(); it != decorations.end(); ++it) {
        if (!decorationRoles.contains(it.key()) || !it.value().isObject()) return false;
        const QJsonObject slotObject = it.value().toObject();
        if (!onlyKeys(slotObject, decorationSlots)) return false;
        QVariantMap resolvedSlots;
        for (auto slotIt = slotObject.begin(); slotIt != slotObject.end(); ++slotIt) {
            if (!slotIt.value().isObject()) return false;
            const QJsonObject slot = slotIt.value().toObject();
            if (!onlyKeys(slot, QSet<QString>{"asset", "tint", "opacity", "scale"})
                || !slot.value("asset").isString()) return false;
            const QString relativeAsset = slot.value("asset").toString();
            const QString path = asset(relativeAsset);
            if (path.isEmpty() || !QFileInfo(path).isFile()
                || !relativeAsset.endsWith(".svg", Qt::CaseInsensitive)
                || !validSvg(path)) return false;
            if (slot.contains("tint") && (!slot.value("tint").isString()
                || !tintRoles.contains(slot.value("tint").toString()))) return false;
            if (slot.contains("opacity") && (!slot.value("opacity").isDouble()
                || !std::isfinite(slot.value("opacity").toDouble())
                || slot.value("opacity").toDouble() < 0
                || slot.value("opacity").toDouble() > 1)) return false;
            if (slot.contains("scale") && (!slot.value("scale").isDouble()
                || !std::isfinite(slot.value("scale").toDouble())
                || slot.value("scale").toDouble() < 0.5
                || slot.value("scale").toDouble() > 2.0)) return false;
            QVariantMap resolvedSlot = slot.toVariantMap();
            resolvedSlot.insert("asset", QUrl::fromLocalFile(path).toString());
            resolvedSlots.insert(slotIt.key(), resolvedSlot);
        }
        resolvedDecorations.insert(it.key(), resolvedSlots);
    }
    for (const char *key : {"structuralSurface", "internalSurface", "card", "focusedCard", "selection", "statusBacking", "overlayBackdrop", "overlaySurface"})
        if (!o.value(QLatin1String(key)).isDouble()) return false;
    for (auto it = o.begin(); it != o.end(); ++it)
        if (!it.value().isDouble() || !std::isfinite(it.value().toDouble()) || it.value().toDouble() < 0 || it.value().toDouble() > 1) return false;
    for (const char *key : {"panel", "card", "row", "media", "status", "overlay"})
        if (!r.value(QLatin1String(key)).isDouble()) return false;
    for (auto it = r.begin(); it != r.end(); ++it)
        if (!it.value().isDouble() || !std::isfinite(it.value().toDouble()) || it.value().toDouble() < 0 || it.value().toDouble() > 128) return false;
    for (const char *key : {"ior", "depth", "refractionPixels", "dispersionIor", "diffusionPixels", "transmission", "bevelWidth", "bulgeStrength", "sceneLightStrength", "sceneLightPixels", "edgeLightStrength"}) {
        const QJsonValue value = g.value(QLatin1String(key));
        if (!value.isDouble() || !std::isfinite(value.toDouble()) || value.toDouble() < 0 || value.toDouble() > 1000) return false;
    }
    if (!g.value("ior").toDouble() || g.value("ior").toDouble() > 3
        || g.value("transmission").toDouble() > 1 || g.value("dispersionIor").toDouble() > 1) return false;
    const QString chromeStyle = chrome.value("style").toString("flat");
    if (chromeStyle != "flat" && chromeStyle != "bevel") return false;
    if (chromeStyle == "bevel") {
        for (const char *key : {"highlight", "light", "shadow", "darkShadow"}) {
            const QString value = chrome.value(QLatin1String(key)).toString();
            if (!value.startsWith('#') || !QColor(value).isValid()) return false;
        }
        if (!chrome.value("width").isDouble() || chrome.value("width").toDouble() < 1
            || chrome.value("width").toDouble() > 8) return false;
    }
    const QVariantMap wallpaperValues = data.value("wallpaper").toObject().toVariantMap();
    QVariantMap values;
    values.insert("id", expectedId);
    values.insert("name", data.value("name").toString(expectedId));
    values.insert("root", QFileInfo(directory).canonicalFilePath());
    values.insert("colors", c.toVariantMap()); values.insert("opacity", o.toVariantMap());
    values.insert("radii", r.toVariantMap()); values.insert("glass", g.toVariantMap());
    values.insert("radiusPolicy", radiusPolicy);
    values.insert("chrome", chrome.toVariantMap()); values.insert("fonts", fontPaths);
    QVariantMap resolvedRoles;
    for (auto it = roleMap.begin(); it != roleMap.end(); ++it) {
        if (!faces.contains(it.value().toString()) || !fontPaths.contains(it.value().toString())) return false;
        resolvedRoles.insert(it.key(), it.value().toString());
    }
    values.insert("icons", iconPaths); values.insert("wallpaper", QUrl::fromLocalFile(wallpaper).toString());
    values.insert("materials", resolvedMaterials);
    values.insert("decorations", resolvedDecorations);
    QVariantMap resolvedMotion = motion.toVariantMap();
    resolvedMotion.insert("roles", motionRoles.toVariantMap());
    values.insert("motion", resolvedMotion);
    values.insert("labels", QVariantMap{{"home", homeLabels.toVariantMap()},
                                        {"views", viewLabels.toVariantMap()}});
    values.insert("textStyles", QVariantMap{{"homeTitle", homeTitle.toVariantMap()},
                                             {"viewTitle", viewTitle.toVariantMap()}});
    values.insert("wallpaperValues", wallpaperValues);
    QVariantMap resolvedFonts = fontPaths;
    resolvedFonts.insert("roles", resolvedRoles);
    values.insert("fonts", resolvedFonts);
    *resolved = values;
    return true;
}

bool ThemeManager::apply(const QVariantMap &theme, bool persist)
{
    m_id = theme.value("id").toString(); m_name = theme.value("name").toString();
    m_radiusPolicy = theme.value("radiusPolicy", QStringLiteral("componentBaseline")).toString();
    m_root = theme.value("root").toString(); m_wallpaper = theme.value("wallpaper").toString();
    m_colors = theme.value("colors").toMap(); m_opacity = theme.value("opacity").toMap();
    m_radii = theme.value("radii").toMap(); m_glass = theme.value("glass").toMap();
    m_chrome = theme.value("chrome").toMap(); m_fonts = theme.value("fonts").toMap();
    m_icons = theme.value("icons").toMap(); m_wallpaperValues = theme.value("wallpaperValues").toMap();
    m_materials = theme.value("materials").toMap();
    m_decorations = theme.value("decorations").toMap();
    m_motion = theme.value("motion").toMap(); m_labels = theme.value("labels").toMap();
    m_textStyles = theme.value("textStyles").toMap();
    if (persist) {
        QSettings settings(QSettings::IniFormat, QSettings::UserScope, "Mudos", "lulu");
        settings.setValue("appearance/theme", m_id);
    }
    emit themeChanged();
    return true;
}

bool ThemeManager::select(const QString &id) { return load(id, true); }
QString ThemeManager::iconUrl(const QString &name) const { return m_icons.value(name).toString(); }
