#pragma once

#include <QObject>
#include <QVariantMap>
#include <QVariantList>

class QFileSystemWatcher;
class QTimer;

class ThemeManager final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString activeId READ activeId NOTIFY themeChanged)
    Q_PROPERTY(QString activeName READ activeName NOTIFY themeChanged)
    Q_PROPERTY(QString themeRoot READ themeRoot NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap colors READ colors NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap opacity READ opacity NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap radii READ radii NOTIFY themeChanged)
    Q_PROPERTY(QString radiusPolicy READ radiusPolicy NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap glass READ glass NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap chrome READ chrome NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap fonts READ fonts NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap motion READ motion NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap labels READ labels NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap textStyles READ textStyles NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap icons READ icons NOTIFY themeChanged)
    Q_PROPERTY(QString wallpaperShader READ wallpaperShader NOTIFY themeChanged)
    Q_PROPERTY(QVariantMap wallpaper READ wallpaper NOTIFY themeChanged)
    Q_PROPERTY(QVariantList themes READ themes NOTIFY themesChanged)
public:
    explicit ThemeManager(QObject *parent = nullptr);
    QString activeId() const { return m_id; }
    QString activeName() const { return m_name; }
    QString themeRoot() const { return m_root; }
    QVariantMap colors() const { return m_colors; }
    QVariantMap opacity() const { return m_opacity; }
    QVariantMap radii() const { return m_radii; }
    QString radiusPolicy() const { return m_radiusPolicy; }
    QVariantMap glass() const { return m_glass; }
    QVariantMap chrome() const { return m_chrome; }
    QVariantMap fonts() const { return m_fonts; }
    QVariantMap motion() const { return m_motion; }
    QVariantMap labels() const { return m_labels; }
    QVariantMap textStyles() const { return m_textStyles; }
    QVariantMap icons() const { return m_icons; }
    QString wallpaperShader() const { return m_wallpaper; }
    QVariantMap wallpaper() const { return m_wallpaperValues; }
    QVariantList themes() const { return m_themes; }
    Q_INVOKABLE bool select(const QString &id);
    Q_INVOKABLE QString iconUrl(const QString &name) const;
signals:
    void themeChanged();
    void themesChanged();
private:
    bool load(const QString &id, bool persist);
    bool inspectAt(const QString &root, const QString &id, QVariantMap *resolved) const;
    bool apply(const QVariantMap &resolved, bool persist);
    void watchSettings();
    QStringList roots() const;
    QString m_id, m_name, m_root, m_wallpaper;
    QString m_radiusPolicy = QStringLiteral("componentBaseline");
    QVariantMap m_colors, m_opacity, m_radii, m_glass, m_chrome, m_fonts, m_icons;
    QVariantMap m_motion, m_labels, m_textStyles;
    QVariantMap m_wallpaperValues;
    QVariantList m_themes;
    QFileSystemWatcher *m_settingsWatcher = nullptr;
    QTimer *m_settingsReload = nullptr;
};
