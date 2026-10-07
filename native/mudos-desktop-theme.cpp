#include "theme-manager.h"

#include <QCoreApplication>
#include <QColor>
#include <QJsonDocument>
#include <QJsonObject>
#include <QVariantMap>

int main(int argc, char **argv)
{
    QCoreApplication application(argc, argv);
    ThemeManager theme;
    const QVariantMap colors = theme.colors();
    const QVariantMap radii = theme.radii();
    const auto color = [&colors](const char *name, const char *fallback) {
        const QColor value(colors.value(QLatin1String(name)).toString());
        return value.isValid() ? value.name(QColor::HexRgb) : QString::fromLatin1(fallback);
    };
    QJsonObject snapshot{
        {"theme", theme.activeId()},
        {"background", color("backdrop", "#202124")},
        {"surface", color("surfaceElevated", "#292a2d")},
        {"primaryText", color("primaryText", "#eeeeee")},
        {"secondaryText", color("secondaryText", "#cccccc")},
        {"accent", color("accent", "#80cbc4")},
        {"focus", color("focusIndicator", "#80cbc4")},
        {"border", color("border", "#555555")},
        {"radius", radii.value("panel", 6).toInt()},
    };
    const QByteArray output = QJsonDocument(snapshot).toJson(QJsonDocument::Compact);
    fwrite(output.constData(), 1, size_t(output.size()), stdout);
    fputc('\n', stdout);
    return 0;
}
