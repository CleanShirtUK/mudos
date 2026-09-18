#pragma once

#include <QImage>
#include <QQuickPaintedItem>
#include <QSize>

#include <memory>

class MudosDisplayUnderlay : public QQuickPaintedItem
{
    Q_OBJECT
    Q_PROPERTY(QSize frameSize READ frameSize NOTIFY frameSizeChanged)
    Q_PROPERTY(bool available READ available NOTIFY availableChanged)

public:
    explicit MudosDisplayUnderlay(QQuickItem *parent = nullptr);
    ~MudosDisplayUnderlay() override;

    QSize frameSize() const { return frameSize_; }
    bool available() const { return available_; }

    void paint(QPainter *painter) override;

signals:
    void frameSizeChanged();
    void availableChanged();

private:
    class Capture;
    std::unique_ptr<Capture> capture_;
    QImage frame_;
    QSize frameSize_;
    bool available_ = false;
    bool loggedFirstFrame_ = false;

    void acceptFrame(const QImage &frame);
};
