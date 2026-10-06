#include "theme-manager.h"

#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QColor>
#include <QDebug>
#include <QStandardPaths>
#include <QFile>
#include <QUrl>
#include <cmath>

namespace {
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
    load(QString(), false);
    for (const QString &base : roots()) {
        QDir dir(base);
        for (const QString &id : dir.entryList(QDir::Dirs | QDir::NoDotAndDotDot)) {
            const QString config = contained(QDir(base).filePath(id), "theme.json");
            if (config.isEmpty()) continue;
            QFile file(config);
            if (!file.open(QIODevice::ReadOnly)) continue;
            const auto json = QJsonDocument::fromJson(file.readAll()).object();
            if (json.value("id").toString() == id && json.value("schema_version").toInt() == 1)
                m_themes.append(QVariantMap{{"id", id}, {"name", json.value("name").toString(id)}});
        }
    }
    emit themesChanged();
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
        id = settings.value("appearance/theme", "mudos-default").toString();
    }
    for (const QString &base : roots())
        if (loadAt(QDir(base).filePath(id), id, persist)) return true;
    if (id != "mudos-default") {
        qWarning() << "Theme invalid or unavailable; falling back to mudos-default:" << id;
        for (const QString &base : roots())
            if (loadAt(QDir(base).filePath("mudos-default"), "mudos-default", persist)) return true;
    }
    return false;
}

bool ThemeManager::loadAt(const QString &directory, const QString &expectedId, bool persist)
{
    const QString configPath = contained(directory, "theme.json");
    QFile config(configPath);
    if (configPath.isEmpty() || !config.open(QIODevice::ReadOnly)) return false;
    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(config.readAll(), &error);
    const QJsonObject data = doc.object();
    if (error.error != QJsonParseError::NoError || !doc.isObject()
        || data.value("schema_version").toInt() != 1 || data.value("id").toString() != expectedId) return false;
    const QJsonObject c = data.value("colors").toObject();
    const QJsonObject o = data.value("opacity").toObject();
    const QJsonObject r = data.value("radii").toObject();
    const QJsonObject g = data.value("glass").toObject();
    const QJsonObject f = data.value("fonts").toObject();
    const QJsonObject faces = f.value("faces").toObject();
    const QJsonObject icons = data.value("icons").toObject();
    auto requiredColor = [&](const char *key) { const QString value = c.value(QLatin1String(key)).toString(); return value.startsWith(QLatin1Char('#')) && QColor(value).isValid(); };
    for (const char *key : {"primaryText", "secondaryText", "mutedText", "selectedText", "accent", "focusIndicator", "warning", "backdrop", "surface", "surfaceElevated", "surfaceInternal", "cardSurface", "focusedCardSurface", "actionSurface", "actionText", "artworkSurface", "border", "focusBorder", "overlayBackdrop", "overlaySurface", "launchOverlaySurface", "guideSurface", "guideBorder", "guideItemSurface", "guideSelectedText", "scrollFadeStart", "scrollFadeEnd"}) if (!requiredColor(key)) return false;
    auto asset = [&](const QString &path) { return contained(directory, path); };
    QVariantMap fontPaths;
    for (auto it = faces.begin(); it != faces.end(); ++it) {
        const QString path = asset(it.value().toObject().value("file").toString());
        if (path.isEmpty() || !QFileInfo(path).isFile()) return false;
        fontPaths.insert(it.key(), QUrl::fromLocalFile(path).toString());
    }
    const QString wallpaper = asset(data.value("wallpaper").toObject().value("shader").toString());
    if (wallpaper.isEmpty() || !QFileInfo(wallpaper).isFile()) return false;
    QVariantMap iconPaths;
    for (auto it = icons.begin(); it != icons.end(); ++it) {
        const QString path = asset(it.value().toString());
        if (path.isEmpty() || !QFileInfo(path).isFile()) return false;
        iconPaths.insert(it.key(), QUrl::fromLocalFile(path).toString());
    }
    for (const char *key : {"structuralSurface", "internalSurface", "card", "focusedCard", "selection", "statusBacking", "overlayBackdrop", "overlaySurface"}) if (!o.value(QLatin1String(key)).isDouble()) return false;
    for (auto it = o.begin(); it != o.end(); ++it) if (!it.value().isDouble() || !std::isfinite(it.value().toDouble()) || it.value().toDouble() < 0 || it.value().toDouble() > 1) return false;
    for (const char *key : {"panel", "card", "row", "media", "status", "overlay"}) if (!r.value(QLatin1String(key)).isDouble()) return false;
    for (auto it = r.begin(); it != r.end(); ++it) if (!it.value().isDouble() || !std::isfinite(it.value().toDouble()) || it.value().toDouble() < 0 || it.value().toDouble() > 128) return false;
    for (const char *key : {"ior", "depth", "refractionPixels", "dispersionIor", "diffusionPixels", "transmission", "bevelWidth", "bulgeStrength", "sceneLightStrength", "sceneLightPixels", "edgeLightStrength"}) {
        const QJsonValue value = g.value(QLatin1String(key));
        if (!value.isDouble() || !std::isfinite(value.toDouble()) || value.toDouble() < 0 || value.toDouble() > 1000) return false;
    }
    if (!g.value("ior").toDouble() || g.value("ior").toDouble() > 3
        || g.value("transmission").toDouble() > 1 || g.value("dispersionIor").toDouble() > 1) return false;
    for (const char *key : {"regular", "bold", "heavy", "icons", "controller"}) if (!faces.contains(QLatin1String(key))) return false;
    for (auto it = icons.begin(); it != icons.end(); ++it) if (!it.value().toString().endsWith(".svg", Qt::CaseInsensitive)) return false;
    m_id = expectedId; m_name = data.value("name").toString(expectedId); m_root = QFileInfo(directory).canonicalFilePath();
    m_colors = c.toVariantMap(); m_opacity = o.toVariantMap(); m_radii = r.toVariantMap(); m_glass = g.toVariantMap();
    m_fonts = fontPaths; m_icons = iconPaths; m_wallpaper = QUrl::fromLocalFile(wallpaper).toString();
    m_wallpaperValues = data.value("wallpaper").toObject().toVariantMap();
    if (persist) { QSettings s(QSettings::IniFormat, QSettings::UserScope, "Mudos", "lulu"); s.setValue("appearance/theme", m_id); }
    emit themeChanged();
    return true;
}

bool ThemeManager::select(const QString &id) { return load(id, true); }
QString ThemeManager::iconUrl(const QString &name) const { return m_icons.value(name).toString(); }
