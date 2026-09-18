#pragma once

#include <QImage>
#include <QQuickItem>
#include <QSize>

#include <memory>

class MudosDisplayUnderlay : public QQuickItem
{
    Q_OBJECT
    Q_PROPERTY(QSize frameSize READ frameSize NOTIFY frameSizeChanged)
    Q_PROPERTY(int frameStride READ frameStride NOTIFY frameStrideChanged)
    Q_PROPERTY(QString sourceFormat READ sourceFormat CONSTANT)
    Q_PROPERTY(QString glassMode READ glassMode CONSTANT)
    Q_PROPERTY(quint64 textureRevision READ textureRevision NOTIFY textureRevisionChanged)
    Q_PROPERTY(bool available READ available NOTIFY availableChanged)
    Q_PROPERTY(bool diagnosticMode READ diagnosticMode CONSTANT)

public:
    explicit MudosDisplayUnderlay(QQuickItem *parent = nullptr);
    ~MudosDisplayUnderlay() override;

    QSize frameSize() const { return frameSize_; }
    int frameStride() const { return frameStride_; }
    QString sourceFormat() const { return QStringLiteral("BGRx -> RGBA8888"); }
    QString glassMode() const { return glassMode_; }
    quint64 textureRevision() const { return textureRevision_; }
    bool available() const { return available_; }
    bool diagnosticMode() const { return diagnosticMode_; }

    bool isTextureProvider() const override;
    QSGTextureProvider *textureProvider() const override;

protected:
    QSGNode *updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *data) override;

signals:
    void frameSizeChanged();
    void frameStrideChanged();
    void textureRevisionChanged();
    void availableChanged();

private:
    class TextureProvider;
    class Capture;
    std::unique_ptr<Capture> capture_;
    std::unique_ptr<TextureProvider> provider_;
    QImage frame_;
    QSize frameSize_;
    int frameStride_ = 0;
    bool available_ = false;
    bool loggedFirstFrame_ = false;
    int frameCount_ = 0;
    const bool diagnosticMode_ = qEnvironmentVariableIsSet("LULU_DISPLAY_UNDERLAY_DIAGNOSTIC");
    const QString glassMode_ = qEnvironmentVariable("LULU_GUIDE_GLASS_MODE", "glass");
    quint64 textureRevision_ = 0;

    void acceptFrame(const QImage &frame, int sourceStride);
};
