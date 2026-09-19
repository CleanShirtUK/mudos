#pragma once

#include <QQuickWindow>

class MudosOverlayWindow : public QQuickWindow
{
    Q_OBJECT

public:
    explicit MudosOverlayWindow(QWindow *parent = nullptr);


protected:
    void showEvent(QShowEvent *event) override;

private:
    void markExternalOverlay();
};
