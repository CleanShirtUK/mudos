.pragma library

function bounds(progress, homeX, homeY, homeWidth, homeHeight,
                fullscreenX, fullscreenY, fullscreenWidth, fullscreenHeight,
                forceExpanded) {
    if (forceExpanded)
        return {x: fullscreenX, y: fullscreenY,
                width: fullscreenWidth, height: fullscreenHeight}
    return {
        x: homeX + (fullscreenX - homeX) * progress,
        y: homeY + (fullscreenY - homeY) * progress,
        width: homeWidth + (fullscreenWidth - homeWidth) * progress,
        height: homeHeight + (fullscreenHeight - homeHeight) * progress
    }
}
