#pragma once

#include <QQuickWindow>

class MudosOverlayWindow : public QQuickWindow
{
    Q_OBJECT

public:
    explicit MudosOverlayWindow(QWindow *parent = nullptr);

    Q_INVOKABLE bool saveDiagnosticFrame(const QString &path);

protected:
    void showEvent(QShowEvent *event) override;

private:
    void markExternalOverlay();
};
