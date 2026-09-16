#include "mudos-glass-item.h"

#include <QDebug>
#include <QDir>
#include <QSGGeometry>
#include <QSGGeometryNode>
#include <QSGMaterial>
#include <QSGMaterialShader>
#include <QSGTextureProvider>
#include <QSGTexture>
#include <QStringList>

#include <cstring>

namespace {

class GlassMaterial;

class GlassShader final : public QSGMaterialShader
{
public:
    GlassShader()
    {
        const QString root = qEnvironmentVariable("LULU_INSTALL_ROOT", "/opt/lulu");
        setShaderFileName(VertexStage, QDir(root).filePath("ui/shaders/mudos-glass.vert.qsb"));
        setShaderFileName(FragmentStage, QDir(root).filePath("ui/shaders/mudos-glass.frag.qsb"));
    }

    bool updateUniformData(RenderState &state, QSGMaterial *newMaterial,
                           QSGMaterial *) override;
    void updateSampledImage(RenderState &, int binding, QSGTexture **texture,
                            QSGMaterial *newMaterial, QSGMaterial *) override;
};

class GlassMaterial final : public QSGMaterial
{
public:
    GlassMaterial()
    {
        setFlag(QSGMaterial::Blending);
    }

    int compare(const QSGMaterial *other) const override
    {
        const int result = QSGMaterial::compare(other);
        return result;
    }

    QSGMaterialType *type() const override
    {
        static QSGMaterialType materialType;
        return &materialType;
    }

    QSGMaterialShader *createShader(QSGRendererInterface::RenderMode) const override
    {
        return new GlassShader;
    }

    QSGTextureProvider *provider = nullptr;
    QSizeF canonicalSize{1280, 720};
    QRectF canonicalRect;
    QSizeF surfaceSize;
    QRectF textureSubRect{0, 0, 1, 1};
    qreal ior = 1.08;
    qreal depth = 0.32;
    qreal refractionPixels = 12;
    qreal dispersionIor = 0;
    qreal diffusionPixels = 0;
    qreal transmission = 1;
    qreal bevelWidthPx = 6;
    qreal bulgeStrength = 0;
    qreal sceneLightStrength = 0;
    qreal sceneLightPixels = 24;
    qreal edgeLightStrength = 0;
    QVector2D edgeLightDirection{1, -1};
    qreal cornerRadius = 0;
    bool transparentOutsideMask = false;
    int diagnostic = 0;
    MudosGlassItem *owner = nullptr;
};

void putFloat(QByteArray &data, int offset, float value)
{
    std::memcpy(data.data() + offset, &value, sizeof(value));
}

void putVec2(QByteArray &data, int offset, const QVector2D &value)
{
    putFloat(data, offset, value.x());
    putFloat(data, offset + 4, value.y());
}

bool GlassShader::updateUniformData(RenderState &state, QSGMaterial *newMaterial,
                                    QSGMaterial *)
{
    auto *material = static_cast<GlassMaterial *>(newMaterial);
    QByteArray *data = state.uniformData();
    data->resize(176);
    const QMatrix4x4 matrix = state.combinedMatrix();
    std::memcpy(data->data(), matrix.constData(), 16 * sizeof(float));
    putFloat(*data, 64, state.opacity());
    putVec2(*data, 72, QVector2D(material->canonicalRect.x(), material->canonicalRect.y()));
    putVec2(*data, 80, QVector2D(material->surfaceSize.width(), material->surfaceSize.height()));
    putVec2(*data, 88, QVector2D(material->canonicalSize.width(), material->canonicalSize.height()));
    putFloat(*data, 96, material->ior);
    putFloat(*data, 100, material->depth);
    putFloat(*data, 104, material->refractionPixels);
    putFloat(*data, 108, material->cornerRadius);
    putFloat(*data, 112, material->dispersionIor);
    putFloat(*data, 116, material->diffusionPixels);
    putFloat(*data, 120, material->transmission);
    putFloat(*data, 124, material->bevelWidthPx);
    putFloat(*data, 128, material->bulgeStrength);
    putFloat(*data, 132, material->sceneLightStrength);
    putFloat(*data, 136, material->sceneLightPixels);
    putFloat(*data, 140, material->edgeLightStrength);
    putVec2(*data, 144, material->edgeLightDirection);
    putFloat(*data, 152, material->transparentOutsideMask ? 1.0f : 0.0f);
    putFloat(*data, 156, static_cast<float>(material->diagnostic));
    putFloat(*data, 160, material->textureSubRect.x());
    putFloat(*data, 164, material->textureSubRect.y());
    putFloat(*data, 168, material->textureSubRect.width());
    putFloat(*data, 172, material->textureSubRect.height());
    if (material->owner)
        material->owner->recordUniformData(*data);
    return true;
}

void GlassShader::updateSampledImage(RenderState &, int binding, QSGTexture **texture,
                                     QSGMaterial *newMaterial, QSGMaterial *)
{
    if (binding == 1) {
        auto *material = static_cast<GlassMaterial *>(newMaterial);
        *texture = material->provider ? material->provider->texture() : nullptr;
    }
}

void copyMaterial(GlassMaterial *material, const MudosGlassItem *item)
{
    material->canonicalSize = item->canonicalSize();
    material->canonicalRect = item->canonicalRect();
    material->surfaceSize = QSizeF(item->width(), item->height());
    material->ior = item->ior();
    material->depth = item->glassDepth();
    material->refractionPixels = item->refractionPixels();
    material->dispersionIor = item->dispersionIor();
    material->diffusionPixels = item->diffusionPixels();
    material->transmission = item->transmission();
    material->bevelWidthPx = item->bevelWidthPx();
    material->bulgeStrength = item->bulgeStrength();
    material->sceneLightStrength = item->sceneLightStrength();
    material->sceneLightPixels = item->sceneLightPixels();
    material->edgeLightStrength = item->edgeLightStrength();
    material->edgeLightDirection = item->edgeLightDirection();
    material->cornerRadius = item->cornerRadius();
    material->transparentOutsideMask = item->transparentOutsideMask();
    material->diagnostic = item->diagnosticMode();
    material->owner = const_cast<MudosGlassItem *>(item);
    material->provider = item->backdrop() && item->backdrop()->isTextureProvider()
        ? item->backdrop()->textureProvider() : nullptr;
    material->textureSubRect = material->provider && material->provider->texture()
        ? material->provider->texture()->normalizedTextureSubRect()
        : QRectF(0, 0, 1, 1);
    static bool loggedTextureBoundary = false;
    const QSGTexture *texture = material->provider ? material->provider->texture() : nullptr;
    if (!loggedTextureBoundary && texture && texture->textureSize().isValid()) {
        loggedTextureBoundary = true;
        qInfo() << "MUDOS_RENDER_CHAIN_QSG_TEXTURE"
                << "itemSize" << QSizeF(item->width(), item->height())
                << "textureSize" << (texture ? texture->textureSize() : QSize())
                << "normalizedSubRect" << material->textureSubRect;
    }
}

} // namespace

MudosGlassItem::MudosGlassItem(QQuickItem *parent)
    : QQuickItem(parent)
{
    setFlag(ItemHasContents, true);
    connect(this, &QQuickItem::widthChanged, this, &QQuickItem::update);
    connect(this, &QQuickItem::heightChanged, this, &QQuickItem::update);
}

void MudosGlassItem::setBackdrop(QQuickItem *backdrop)
{
    if (m_backdrop == backdrop)
        return;
    m_backdrop = backdrop;
    emit backdropChanged();
    update();
}

void MudosGlassItem::setCanonicalSize(const QSizeF &size)
{
    if (m_canonicalSize == size)
        return;
    m_canonicalSize = size;
    emit canonicalSizeChanged();
    update();
}

void MudosGlassItem::setCanonicalRect(const QRectF &rect)
{
    if (m_canonicalRect == rect)
        return;
    m_canonicalRect = rect;
    emit canonicalRectChanged();
    update();
}

#define MUDOS_GLASS_REAL_SETTER(name, member) \
    void MudosGlassItem::set##name(qreal value) { \
        if (qFuzzyCompare(member, value)) return; member = value; emit opticsChanged(); update(); }
MUDOS_GLASS_REAL_SETTER(Ior, m_ior)
MUDOS_GLASS_REAL_SETTER(GlassDepth, m_glassDepth)
MUDOS_GLASS_REAL_SETTER(RefractionPixels, m_refractionPixels)
MUDOS_GLASS_REAL_SETTER(DispersionIor, m_dispersionIor)
MUDOS_GLASS_REAL_SETTER(DiffusionPixels, m_diffusionPixels)
MUDOS_GLASS_REAL_SETTER(Transmission, m_transmission)
MUDOS_GLASS_REAL_SETTER(BevelWidthPx, m_bevelWidthPx)
MUDOS_GLASS_REAL_SETTER(BulgeStrength, m_bulgeStrength)
MUDOS_GLASS_REAL_SETTER(SceneLightStrength, m_sceneLightStrength)
MUDOS_GLASS_REAL_SETTER(SceneLightPixels, m_sceneLightPixels)
MUDOS_GLASS_REAL_SETTER(EdgeLightStrength, m_edgeLightStrength)
MUDOS_GLASS_REAL_SETTER(CornerRadius, m_cornerRadius)
#undef MUDOS_GLASS_REAL_SETTER

void MudosGlassItem::setEdgeLightDirection(const QVector2D &value)
{
    if (m_edgeLightDirection == value) return;
    m_edgeLightDirection = value; emit opticsChanged(); update();
}

void MudosGlassItem::setTransparentOutsideMask(bool value)
{
    if (m_transparentOutsideMask == value) return;
    m_transparentOutsideMask = value; emit opticsChanged(); update();
}

void MudosGlassItem::setDiagnosticMode(int value)
{
    if (m_diagnosticMode == value) return;
    m_diagnosticMode = value; emit opticsChanged(); update();
}

QSGNode *MudosGlassItem::updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *data)
{
    Q_UNUSED(data)
    auto *node = static_cast<QSGGeometryNode *>(oldNode);
    if (!node) {
        auto *geometry = new QSGGeometry(QSGGeometry::defaultAttributes_TexturedPoint2D(), 4);
        geometry->setDrawingMode(QSGGeometry::DrawTriangleStrip);
        geometry->setVertexDataPattern(QSGGeometry::DynamicPattern);
        node = new QSGGeometryNode;
        node->setGeometry(geometry);
        node->setFlag(QSGNode::OwnsGeometry);
        node->setMaterial(new GlassMaterial);
        node->setFlag(QSGNode::OwnsMaterial);
    }

    auto *geometry = node->geometry();
    auto *vertices = geometry->vertexDataAsTexturedPoint2D();
    vertices[0].set(0, 0, 0, 0);
    vertices[1].set(width(), 0, 1, 0);
    vertices[2].set(0, height(), 0, 1);
    vertices[3].set(width(), height(), 1, 1);
    geometry->markVertexDataDirty();

    auto *material = static_cast<GlassMaterial *>(node->material());
    copyMaterial(material, this);
    m_lastMaterialAddress = reinterpret_cast<quintptr>(material);
    node->markDirty(QSGNode::DirtyGeometry | QSGNode::DirtyMaterial);
    m_lastRenderMatrix = data && data->transformNode
        ? data->transformNode->combinedMatrix() : QMatrix4x4();
    return node;
}

void MudosGlassItem::releaseResources()
{
    update();
}

void MudosGlassItem::dumpMapping() const
{
    const qreal sourceWidth = m_backdrop ? m_backdrop->width() : 0;
    const qreal sourceHeight = m_backdrop ? m_backdrop->height() : 0;
    const QRectF uvRect(
        m_canonicalRect.x() / m_canonicalSize.width(),
        m_canonicalRect.y() / m_canonicalSize.height(),
        m_canonicalRect.width() / m_canonicalSize.width(),
        m_canonicalRect.height() / m_canonicalSize.height());
    qInfo().noquote() << "MUDOS_GLASS_POC_MAPPING"
                      << "itemAddress" << static_cast<const void *>(this)
                      << "materialAddress" << reinterpret_cast<const void *>(m_lastMaterialAddress)
                      << "item" << width() << height()
                      << "canonicalRect" << m_canonicalRect
                      << "canonicalSize" << m_canonicalSize
                      << "sourceTextureSize" << QSizeF(sourceWidth, sourceHeight)
                      << "uvRect" << uvRect
                      << "renderMatrix" << m_lastRenderMatrix;
}

void MudosGlassItem::recordUniformData(const QByteArray &data)
{
    m_lastUniformData = data;
}

void MudosGlassItem::dumpRuntimeState(const QPointF &position) const
{
    const QSGTexture *texture = nullptr;
    if (m_backdrop && m_backdrop->isTextureProvider())
        texture = m_backdrop->textureProvider()->texture();

    QStringList offsets;
    for (int offset = 0; offset + 4 <= m_lastUniformData.size(); offset += 4) {
        float value = 0;
        std::memcpy(&value, m_lastUniformData.constData() + offset, sizeof(value));
        offsets.append(QStringLiteral("%1:%2").arg(offset).arg(value, 0, 'g', 9));
    }
    float effectiveOpacity = 0;
    if (m_lastUniformData.size() >= 68)
        std::memcpy(&effectiveOpacity, m_lastUniformData.constData() + 64, sizeof(effectiveOpacity));

    qInfo() << "MUDOS_NATIVE_GLASS_RUNTIME"
            << "itemAddress" << static_cast<const void *>(this)
            << "canonicalSize" << m_canonicalSize
            << "canonicalRect" << m_canonicalRect
            << "surfaceSize" << QSizeF(width(), height())
            << "sourceLogicalSize" << (m_backdrop ? QSizeF(m_backdrop->width(), m_backdrop->height()) : QSizeF())
            << "sourceNativeSize" << (texture ? texture->textureSize() : QSize())
            << "normalizedSubRect" << (texture ? texture->normalizedTextureSubRect() : QRectF())
            << "filtering" << (texture ? texture->filtering() : QSGTexture::None)
            << "mipmapFiltering" << (texture ? texture->mipmapFiltering() : QSGTexture::None)
            << "hasMipmaps" << (texture ? texture->hasMipmaps() : false)
            << "hasAlpha" << (texture ? texture->hasAlphaChannel() : false)
            << "anisotropy" << (texture ? texture->anisotropyLevel() : QSGTexture::AnisotropyNone)
            << "horizontalWrap" << (texture ? texture->horizontalWrapMode() : QSGTexture::ClampToEdge)
            << "verticalWrap" << (texture ? texture->verticalWrapMode() : QSGTexture::ClampToEdge)
            << "effectiveOpacity" << effectiveOpacity
            << "ior" << m_ior << "depth" << m_glassDepth
            << "refractionPx" << m_refractionPixels
            << "dispersion" << m_dispersionIor
            << "diffusionPx" << m_diffusionPixels
            << "transmission" << m_transmission
            << "bevelPx" << m_bevelWidthPx
            << "bulge" << m_bulgeStrength
            << "edgeLight" << m_edgeLightStrength
            << "edgeDirection" << m_edgeLightDirection
            << "sceneLight" << m_sceneLightStrength << m_sceneLightPixels
            << "radius" << m_cornerRadius
            << "transparentOutsideMask" << m_transparentOutsideMask
            << "presentationPosition" << position
            << "uniformBytes" << m_lastUniformData.size()
            << "uniformHex" << m_lastUniformData.toHex()
            << "uniformFloatOffsets" << offsets;
}
