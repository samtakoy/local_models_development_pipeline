/**
 * Client-side JavaScript for the Card Viewer Library.
 * Handles AJAX add/remove operations without page reload.
 *
 * Functions:
 *   - loadLibrary()      — fetches and renders library data from /api/sources
 *   - addSource(path, topicId) — POST to /api/sources/add
 *   - removeSource(id)   — DELETE to /api/sources/<id>
 */

let currentData = null;

/** Fetch latest library data and render. */
async function loadLibrary() {
    try {
        const response = await fetch('/api/sources');
        if (!response.ok) throw new Error('Failed to fetch library');
        currentData = await response.json();
        renderLibrary(currentData);
    } catch (err) {
        console.error('loadLibrary error:', err);
        showToast('Failed to load library: ' + err.message, 'error');
    }
}

/** Add a source via AJAX. */
async function addSource(path, topicId) {
    try {
        const response = await fetch('/api/sources/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path, topic_id: topicId }),
        });

        if (response.ok) {
            currentData = await response.json();
            renderLibrary(currentData);
            showToast('Source added successfully!', 'success');
        } else {
            const errData = await response.json().catch(() => ({}));
            showToast(errData.error || 'Failed to add source', 'error');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
    }
}

/** Remove a source via AJAX. */
async function removeSource(sourceId) {
    try {
        const response = await fetch(`/api/sources/${sourceId}`, {
            method: 'DELETE',
        });

        if (response.ok) {
            currentData = await response.json();
            renderLibrary(currentData);
            showToast('Source removed.', 'success');
        } else {
            const errData = await response.json().catch(() => ({}));
            showToast(errData.error || 'Failed to remove source', 'error');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
    }
}

/** Render library data into the DOM. */
function renderLibrary(data) {
    if (!data || !data.topics) return;

    const container = document.getElementById('library-content');
    if (data.topics.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No sources yet.</p></div>';
        return;
    }

    let html = '';
    for (const topic of data.topics) {
        html += `<div class="topic-section">`;
        html += `<div class="topic-header"><h2>${escapeHtml(topic.name)}</h2>`;
        if (topic.is_default) {
            html += '<span class="badge-default">Default</span>';
        }
        html += `</div>`;

        if (topic.sources.length === 0) {
            html += '<p style="color: var(--text-muted); font-size: 0.9rem;">No sources in this topic.</p>';
        } else {
            html += '<div class="sources-list">';
            for (const source of topic.sources) {
                const icon = source.type === 'folder' ? '&#x1F4C1;' : '&#x1F4C4;';
                html += `<div class="source-card">`;
                html += `<span class="source-icon">${icon}</span>`;
                html += '<div class="source-info">';

                if (source.decks.length > 0) {
                    html += `<div class="source-title" onclick="event.stopPropagation(); viewDeck('${source.id}')" style="cursor:pointer;">${escapeHtml(source.decks[0].title)}</div>`;
                } else {
                    html += `<div class="source-title" onclick="viewDeck('${source.id}')" style="cursor:pointer;">Empty deck</div>`;
                }

                html += `<div class="source-path">${shortenPath(source.path)}</div>`;

                let statusClass = '', statusText = '';
                if (source.decks.length > 0) {
                    const allOk = source.decks.every(d => d.status === 'ok');
                    const anyMissing = source.decks.some(d => d.status === 'missing');
                    if (anyMissing && !allOk) {
                        statusClass = 'status-missing';
                        statusText = 'Partial';
                    } else if (allOk) {
                        statusClass = 'status-ok';
                        statusText = 'OK';
                    }
                }
                if (statusClass) {
                    html += `<div class="source-meta"><span class="status-badge ${statusClass}">${statusText}</span></div>`;
                }

                html += `</div>`; // source-info
                html += `<button class="btn btn-danger" onclick="event.stopPropagation(); removeSource('${source.id}')" style="cursor:pointer;">Remove</button>`;
                html += `</div>`; // source-card
            }
            html += '</div>'; // sources-list
        }
        html += '</div>'; // topic-section
    }
    container.innerHTML = html;
}

/** Navigate to the deck viewer for a source. */
function viewDeck(sourceId) {
    window.location.href = '/deck/' + sourceId;
}

function shortenPath(path) {
    if (!path || path.length <= 60) return path;
    const parts = path.split('/');
    if (parts.length > 3) {
        return '.../' + parts.slice(-2).join('/');
    }
    return path;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type) {
    // Simple toast: in real app would use a container
    console[type === 'error' ? 'error' : 'log']('[toast] ' + message);
}
