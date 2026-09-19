#pragma once

#include <QColor>
#include <QByteArray>
#include <QMatrix4x4>
#include <QPointer>
#include <QQuickItem>
#include <QRectF>
#include <QSGTextureProvider>
#include <QSizeF>

class MudosGlassItem : public QQuickItem
{
    Q_OBJECT
    Q_PROPERTY(QQuickItem *backdrop READ backdrop WRITE setBackdrop NOTIFY backdropChanged)
    Q_PROPERTY(QSizeF canonicalSize READ canonicalSize WRITE setCanonicalSize NOTIFY canonicalSizeChanged)
    Q_PROPERTY(QRectF canonicalRect READ canonicalRect WRITE setCanonicalRect NOTIFY canonicalRectChanged)
    Q_PROPERTY(qreal ior READ ior WRITE setIor NOTIFY opticsChanged)
    Q_PROPERTY(qreal glassDepth READ glassDepth WRITE setGlassDepth NOTIFY opticsChanged)
    Q_PROPERTY(qreal refractionPixels READ refractionPixels WRITE setRefractionPixels NOTIFY opticsChanged)
    Q_PROPERTY(qreal dispersionIor READ dispersionIor WRITE setDispersionIor NOTIFY opticsChanged)
    Q_PROPERTY(qreal diffusionPixels READ diffusionPixels WRITE setDiffusionPixels NOTIFY opticsChanged)
    Q_PROPERTY(qreal transmission READ transmission WRITE setTransmission NOTIFY opticsChanged)
    Q_PROPERTY(qreal bevelWidthPx READ bevelWidthPx WRITE setBevelWidthPx NOTIFY opticsChanged)
    Q_PROPERTY(qreal bulgeStrength READ bulgeStrength WRITE setBulgeStrength NOTIFY opticsChanged)
    Q_PROPERTY(qreal sceneLightStrength READ sceneLightStrength WRITE setSceneLightStrength NOTIFY opticsChanged)
    Q_PROPERTY(qreal sceneLightPixels READ sceneLightPixels WRITE setSceneLightPixels NOTIFY opticsChanged)
    Q_PROPERTY(qreal edgeLightStrength READ edgeLightStrength WRITE setEdgeLightStrength NOTIFY opticsChanged)
    Q_PROPERTY(QVector2D edgeLightDirection READ edgeLightDirection WRITE setEdgeLightDirection NOTIFY opticsChanged)
    Q_PROPERTY(qreal cornerRadius READ cornerRadius WRITE setCornerRadius NOTIFY opticsChanged)
    Q_PROPERTY(bool transparentOutsideMask READ transparentOutsideMask WRITE setTransparentOutsideMask NOTIFY opticsChanged)

public:
    explicit MudosGlassItem(QQuickItem *parent = nullptr);

    QQuickItem *backdrop() const { return m_backdrop; }
    void setBackdrop(QQuickItem *backdrop);
    QSizeF canonicalSize() const { return m_canonicalSize; }
    void setCanonicalSize(const QSizeF &size);
    QRectF canonicalRect() const { return m_canonicalRect; }
    void setCanonicalRect(const QRectF &rect);

    qreal ior() const { return m_ior; }
    void setIor(qreal value);
    qreal glassDepth() const { return m_glassDepth; }
    void setGlassDepth(qreal value);
    qreal refractionPixels() const { return m_refractionPixels; }
    void setRefractionPixels(qreal value);
    qreal dispersionIor() const { return m_dispersionIor; }
    void setDispersionIor(qreal value);
    qreal diffusionPixels() const { return m_diffusionPixels; }
    void setDiffusionPixels(qreal value);
    qreal transmission() const { return m_transmission; }
    void setTransmission(qreal value);
    qreal bevelWidthPx() const { return m_bevelWidthPx; }
    void setBevelWidthPx(qreal value);
    qreal bulgeStrength() const { return m_bulgeStrength; }
    void setBulgeStrength(qreal value);
    qreal sceneLightStrength() const { return m_sceneLightStrength; }
    void setSceneLightStrength(qreal value);
    qreal sceneLightPixels() const { return m_sceneLightPixels; }
    void setSceneLightPixels(qreal value);
    qreal edgeLightStrength() const { return m_edgeLightStrength; }
    void setEdgeLightStrength(qreal value);
    QVector2D edgeLightDirection() const { return m_edgeLightDirection; }
    void setEdgeLightDirection(const QVector2D &value);
    qreal cornerRadius() const { return m_cornerRadius; }
    void setCornerRadius(qreal value);
    bool transparentOutsideMask() const { return m_transparentOutsideMask; }
    void setTransparentOutsideMask(bool value);

signals:
    void backdropChanged();
    void canonicalSizeChanged();
    void canonicalRectChanged();
    void opticsChanged();

protected:
    QSGNode *updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *data) override;
    void releaseResources() override;

private:
    QPointer<QQuickItem> m_backdrop;
    QSizeF m_canonicalSize{1280, 720};
    QRectF m_canonicalRect{0, 0, 0, 0};
    qreal m_ior = 1.08;
    qreal m_glassDepth = 0.32;
    qreal m_refractionPixels = 12;
    qreal m_dispersionIor = 0;
    qreal m_diffusionPixels = 0;
    qreal m_transmission = 1;
    qreal m_bevelWidthPx = 6;
    qreal m_bulgeStrength = 0;
    qreal m_sceneLightStrength = 0;
    qreal m_sceneLightPixels = 24;
    qreal m_edgeLightStrength = 0;
    QVector2D m_edgeLightDirection{1, -1};
    qreal m_cornerRadius = 0;
    bool m_transparentOutsideMask = false;
};
