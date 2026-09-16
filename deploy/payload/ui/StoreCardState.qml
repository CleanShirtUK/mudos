import QtQml

// Stable QObject state for one Store card. Catalogue identity remains in game;
// acquisition fields are updated independently without replacing the card.
QtObject {
    property var game: null
    property var acquisitionJob: null
    property string acquisition_state: ""
    property real acquisition_progress: 0
    property bool acquisition_progress_known: false
    property string acquisition_stage: ""
    property var acquisition_error: null
    property string acquisition_signature: ""

    function setAcquisition(job) {
        var signature = job ? JSON.stringify({job_id: job.job_id, state: job.state,
            progress: job.progress, downloaded_bytes: job.downloaded_bytes,
            total_bytes: job.total_bytes, stage: job.stage, error: job.error,
            retryable: job.retryable}) : ""
        if (signature === acquisition_signature)
            return
        acquisition_signature = signature
        acquisitionJob = job || null
        acquisition_state = job ? String(job.state || "") : ""
        acquisition_progress_known = !!job && job.progress !== null
            && job.progress !== undefined
        acquisition_progress = acquisition_progress_known ? Number(job.progress) : 0
        acquisition_stage = job ? String(job.stage || "") : ""
        acquisition_error = job ? (job.error || null) : null
    }
}
