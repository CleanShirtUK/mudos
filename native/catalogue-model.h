#pragma once

#include <QAbstractListModel>
#include <QByteArray>
#include <QHash>
#include <QVariantMap>

class QDBusPendingCallWatcher;

class CatalogueModel final : public QAbstractListModel
{
    Q_OBJECT
    Q_PROPERTY(qulonglong generation READ generation NOTIFY generationChanged)

public:
    explicit CatalogueModel(QObject *parent = nullptr);

    enum Role {
        GameIdRole = Qt::UserRole + 1,
        ProviderRole, ProviderIdRole, TitleRole, PlatformRole, InstallStateRole,
        LaunchableRole, InstallDirRole, ArtworkUrlRole, LastPlayedRole, RuntimeRole,
        PlatformLabelRole, SourceTitleRole, NormalizedSearchTitleRole,
        MetadataProviderRole, MetadataGameIdRole, CanonicalTitleRole, MatchStatusRole,
        MatchMethodRole, MatchConfidenceRole, MatchLockedRole, MetadataCheckedAtRole,
        DisplayTitleOverrideRole, ArtworkSuppressedRole, AvailabilityStateRole,
        ProviderRecordIdRole, ContentIdentityRole, CatalogueSourceRole, GenresRole,
        GameModesRole, ReleaseDateRole, ReleaseYearRole, TotalPlaytimeRole, LocalMultiplayerRole,
        OnlineMultiplayerRole, GameModeRole, ProtondbRatingRole, LastSeenAtRole,
        LastSyncedAtRole, ArtworkSourceUrlRole, MetadataResolverVersionRole,
        InstalledGameIdRole
    };
    Q_ENUM(Role)

    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    qulonglong generation() const { return generation_; }
    Q_INVOKABLE QVariantMap game(const QString &gameId) const;

    // These methods are also the deterministic seam for native model tests.
    bool loadSnapshot(qulonglong generation, const QByteArray &json, QString *error = nullptr);
    bool applyChanges(qulonglong expectedGeneration, const QByteArray &json, QString *error = nullptr);

signals:
    void generationChanged();
    void synchronizationFailed(const QString &error);

private slots:
    void onCatalogueGenerationChanged(qulonglong generation);
    void onSnapshotFinished(QDBusPendingCallWatcher *watcher);
    void onChangesFinished(QDBusPendingCallWatcher *watcher);

private:
    void requestSnapshot();
    void requestChanges();
    bool applyDelta(const QVariantMap &delta, QString *error);
    void setError(QString *error, const QString &message) const;
    int roleForField(const QString &field) const;

    QVector<QVariantMap> rows_;
    QHash<QString, int> rowById_;
    QHash<int, QByteArray> roles_;
    qulonglong generation_ = 0;
    qulonglong pendingGeneration_ = 0;
    bool snapshotInFlight_ = false;
    bool changesInFlight_ = false;
};
