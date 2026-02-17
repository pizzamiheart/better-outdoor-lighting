// RAW Photo Batch Processor - Frontend Logic

// State
const state = {
    files: [],           // [{file_id, filename, selected}]
    activeFileId: null,  // Currently previewed file
    settings: {
        exposure: 1.0,
        warmth: 0.0,
        contrast: 1.0,
        shadows: 0.0,
        highlights: 0.0,
        clarity: 0.0,
        vibrance: 0.0,
        vignette: 0.0,
        sharpness: 1.0
    },
    previewDebounce: null,
    compareMode: false,
    beforeImageUrl: null,
    afterImageUrl: null
};

// DOM Elements
const elements = {
    uploadZone: document.getElementById('uploadZone'),
    fileInput: document.getElementById('fileInput'),
    previewImage: document.getElementById('previewImage'),
    previewLoading: document.getElementById('previewLoading'),
    previewContainer: document.getElementById('previewContainer'),
    previewPlaceholder: document.getElementById('previewPlaceholder'),
    fileList: document.getElementById('fileList'),
    fileCount: document.getElementById('fileCount'),
    progressSection: document.getElementById('progressSection'),
    progressFill: document.getElementById('progressFill'),
    progressStatus: document.getElementById('progressStatus'),
    progressPercent: document.getElementById('progressPercent'),
    progressDetail: document.getElementById('progressDetail'),
    downloadSection: document.getElementById('downloadSection'),
    downloadLinks: document.getElementById('downloadLinks'),
    downloadSummary: document.getElementById('downloadSummary'),

    // Comparison slider
    compareToggle: document.getElementById('compareToggle'),
    comparisonContainer: document.getElementById('comparisonContainer'),
    comparisonBefore: document.getElementById('comparisonBefore'),
    comparisonSlider: document.getElementById('comparisonSlider'),
    beforeImage: document.getElementById('beforeImage'),
    afterImage: document.getElementById('afterImage'),

    // Filename input
    exportFilename: document.getElementById('exportFilename'),

    // Sliders
    exposure: document.getElementById('exposure'),
    warmth: document.getElementById('warmth'),
    contrast: document.getElementById('contrast'),
    shadows: document.getElementById('shadows'),
    highlights: document.getElementById('highlights'),
    clarity: document.getElementById('clarity'),
    vibrance: document.getElementById('vibrance'),
    vignette: document.getElementById('vignette'),
    sharpness: document.getElementById('sharpness'),

    // Buttons
    btnLandscapeLighting: document.getElementById('btnLandscapeLighting'),
    btnReset: document.getElementById('btnReset'),
    btnSelectAll: document.getElementById('btnSelectAll'),
    btnExportSelected: document.getElementById('btnExportSelected'),
    btnExportAll: document.getElementById('btnExportAll'),
    btnDownloadAll: document.getElementById('btnDownloadAll')
};

// Initialize
function init() {
    setupUploadZone();
    setupSliders();
    setupButtons();
    setupComparisonSlider();
}

// Upload Zone Setup
function setupUploadZone() {
    const zone = elements.uploadZone;

    // Click to upload
    zone.addEventListener('click', () => elements.fileInput.click());

    // File input change
    elements.fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
        e.target.value = ''; // Reset input
    });

    // Drag and drop
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
}

// Handle uploaded files
async function handleFiles(files) {
    for (const file of files) {
        await uploadFile(file);
    }
    updateUI();
}

// Upload single file
async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            state.files.push({
                file_id: data.file_id,
                filename: data.filename,
                selected: true
            });

            // Auto-select first uploaded file for preview
            if (!state.activeFileId) {
                selectFile(data.file_id);
            }
        } else {
            alert(`Upload failed: ${data.error}`);
        }
    } catch (err) {
        alert(`Upload failed: ${err.message}`);
    }
}

// Select file for preview
function selectFile(fileId) {
    state.activeFileId = fileId;
    state.beforeImageUrl = null; // Reset before image cache
    updatePreview();
    updateFileList();
}

// Update preview image
async function updatePreview() {
    if (!state.activeFileId) return;

    // Debounce to avoid too many requests
    if (state.previewDebounce) {
        clearTimeout(state.previewDebounce);
    }

    state.previewDebounce = setTimeout(async () => {
        showPreviewLoading(true);

        const params = new URLSearchParams(state.settings);
        const afterUrl = `/preview/${state.activeFileId}?${params}`;

        try {
            // Fetch the processed (after) image
            const response = await fetch(afterUrl);
            if (response.ok) {
                const blob = await response.blob();
                const objectUrl = URL.createObjectURL(blob);

                // Update standard preview
                elements.previewImage.src = objectUrl;
                elements.previewImage.style.display = state.compareMode ? 'none' : 'block';
                elements.previewPlaceholder.style.display = 'none';

                // Update comparison after image
                state.afterImageUrl = objectUrl;
                elements.afterImage.src = objectUrl;

                // Load before image if in compare mode and not cached
                if (state.compareMode && !state.beforeImageUrl) {
                    await loadBeforeImage();
                }

                updateComparisonView();
            }
        } catch (err) {
            console.error('Preview failed:', err);
        }

        showPreviewLoading(false);
    }, 300);
}

// Load the "before" (unprocessed) image
async function loadBeforeImage() {
    if (!state.activeFileId) return;

    // Fetch with default settings (no adjustments)
    const defaultSettings = {
        exposure: 1.0,
        warmth: 0.0,
        contrast: 1.0,
        shadows: 0.0,
        highlights: 0.0,
        clarity: 0.0,
        vibrance: 0.0,
        vignette: 0.0,
        sharpness: 1.0
    };
    const params = new URLSearchParams(defaultSettings);
    const beforeUrl = `/preview/${state.activeFileId}?${params}`;

    try {
        const response = await fetch(beforeUrl);
        if (response.ok) {
            const blob = await response.blob();
            state.beforeImageUrl = URL.createObjectURL(blob);
            elements.beforeImage.src = state.beforeImageUrl;
        }
    } catch (err) {
        console.error('Failed to load before image:', err);
    }
}

function showPreviewLoading(show) {
    elements.previewLoading.style.display = show ? 'flex' : 'none';
}

// Comparison Slider Setup
function setupComparisonSlider() {
    // Toggle comparison mode
    elements.compareToggle.addEventListener('change', async () => {
        state.compareMode = elements.compareToggle.checked;

        if (state.compareMode && state.activeFileId) {
            // Load before image if not cached
            if (!state.beforeImageUrl) {
                showPreviewLoading(true);
                await loadBeforeImage();
                showPreviewLoading(false);
            }
        }

        updateComparisonView();
    });

    // Slider drag functionality
    let isDragging = false;

    const handleDrag = (e) => {
        if (!isDragging) return;

        const container = elements.comparisonContainer;
        const rect = container.getBoundingClientRect();
        const x = (e.clientX || e.touches[0].clientX) - rect.left;
        const percent = Math.max(0, Math.min(100, (x / rect.width) * 100));

        elements.comparisonBefore.style.width = `${percent}%`;
        elements.comparisonSlider.style.left = `${percent}%`;
    };

    elements.comparisonSlider.addEventListener('mousedown', () => {
        isDragging = true;
        document.body.style.cursor = 'ew-resize';
    });

    document.addEventListener('mousemove', handleDrag);

    document.addEventListener('mouseup', () => {
        isDragging = false;
        document.body.style.cursor = '';
    });

    // Touch support
    elements.comparisonSlider.addEventListener('touchstart', () => {
        isDragging = true;
    });

    document.addEventListener('touchmove', handleDrag);

    document.addEventListener('touchend', () => {
        isDragging = false;
    });
}

// Update comparison view visibility
function updateComparisonView() {
    if (state.compareMode && state.activeFileId) {
        elements.previewImage.style.display = 'none';
        elements.comparisonContainer.style.display = 'block';

        // Reset slider position to middle
        elements.comparisonBefore.style.width = '50%';
        elements.comparisonSlider.style.left = '50%';
    } else {
        elements.comparisonContainer.style.display = 'none';
        if (state.activeFileId) {
            elements.previewImage.style.display = 'block';
        }
    }
}

// Slider Setup
function setupSliders() {
    const sliders = ['exposure', 'warmth', 'contrast', 'shadows', 'highlights', 'clarity', 'vibrance', 'vignette', 'sharpness'];

    sliders.forEach(name => {
        const slider = elements[name];
        const valueDisplay = document.getElementById(`${name}Value`);

        slider.addEventListener('input', () => {
            const value = parseFloat(slider.value);
            state.settings[name] = value;
            valueDisplay.textContent = value.toFixed(2);
            updatePreview();
        });
    });
}

// Update slider UI from settings
function updateSlidersFromSettings() {
    const sliders = ['exposure', 'warmth', 'contrast', 'shadows', 'highlights', 'clarity', 'vibrance', 'vignette', 'sharpness'];

    sliders.forEach(name => {
        const slider = elements[name];
        const valueDisplay = document.getElementById(`${name}Value`);
        const value = state.settings[name];

        slider.value = value;
        valueDisplay.textContent = value.toFixed(2);
    });
}

// Button Setup
function setupButtons() {
    // Landscape Lighting Preset
    elements.btnLandscapeLighting.addEventListener('click', async () => {
        try {
            const response = await fetch('/preset/landscape-lighting');
            const preset = await response.json();
            state.settings = { ...preset };
            updateSlidersFromSettings();
            updatePreview();
        } catch (err) {
            console.error('Failed to load preset:', err);
        }
    });

    // Reset
    elements.btnReset.addEventListener('click', async () => {
        try {
            const response = await fetch('/preset/default');
            const defaults = await response.json();
            state.settings = { ...defaults };
            updateSlidersFromSettings();
            updatePreview();
        } catch (err) {
            console.error('Failed to reset:', err);
        }
    });

    // Select All
    elements.btnSelectAll.addEventListener('click', () => {
        const allSelected = state.files.every(f => f.selected);
        state.files.forEach(f => f.selected = !allSelected);
        updateUI();
    });

    // Export Selected
    elements.btnExportSelected.addEventListener('click', () => {
        const selectedIds = state.files.filter(f => f.selected).map(f => f.file_id);
        if (selectedIds.length > 0) {
            startBatchExport(selectedIds);
        }
    });

    // Export All
    elements.btnExportAll.addEventListener('click', () => {
        const allIds = state.files.map(f => f.file_id);
        if (allIds.length > 0) {
            startBatchExport(allIds);
        }
    });

    // Download All
    elements.btnDownloadAll.addEventListener('click', () => {
        const links = elements.downloadLinks.querySelectorAll('a');
        links.forEach((link, i) => {
            setTimeout(() => link.click(), i * 200);
        });
    });
}

// Get custom filename for export
function getCustomFilename() {
    const input = elements.exportFilename.value.trim();
    return input || null;
}

// Start batch export
async function startBatchExport(fileIds) {
    elements.progressSection.style.display = 'block';
    elements.downloadSection.style.display = 'none';
    elements.progressFill.style.width = '0%';

    const customFilename = getCustomFilename();

    try {
        const response = await fetch('/batch/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_ids: fileIds,
                settings: state.settings,
                custom_filename: customFilename
            })
        });

        const { batch_id } = await response.json();
        monitorBatchProgress(batch_id);
    } catch (err) {
        alert(`Batch export failed: ${err.message}`);
        elements.progressSection.style.display = 'none';
    }
}

// Monitor batch progress via SSE
function monitorBatchProgress(batchId) {
    const eventSource = new EventSource(`/batch/progress/${batchId}`);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.error) {
            eventSource.close();
            alert(data.error);
            elements.progressSection.style.display = 'none';
            return;
        }

        // Update progress UI
        const percent = Math.round((data.current / data.total) * 100);
        elements.progressFill.style.width = `${percent}%`;
        elements.progressPercent.textContent = `${percent}%`;
        elements.progressStatus.textContent = data.status === 'complete' ? 'Complete!' : 'Processing...';
        elements.progressDetail.textContent = data.current_file ? `Processing: ${data.current_file}` : '';

        if (data.done) {
            eventSource.close();
            showDownloadResults(data.results);
        }
    };

    eventSource.onerror = () => {
        eventSource.close();
    };
}

// Show download results
function showDownloadResults(results) {
    elements.downloadSection.style.display = 'block';

    const successCount = results.filter(r => r.success).length;
    elements.downloadSummary.textContent = `${successCount} of ${results.length} files processed successfully`;

    elements.downloadLinks.innerHTML = results.map(r => `
        <div class="download-link">
            <span>${r.filename}</span>
            ${r.success
                ? `<a href="${r.download_url}" download="${r.filename}">Download</a>`
                : `<span class="status error">Failed</span>`
            }
        </div>
    `).join('');
}

// Update file list UI
function updateFileList() {
    if (state.files.length === 0) {
        elements.fileList.innerHTML = '<p class="file-list-empty">No files uploaded yet</p>';
        return;
    }

    elements.fileList.innerHTML = state.files.map(f => `
        <div class="file-item ${f.selected ? 'selected' : ''} ${f.file_id === state.activeFileId ? 'active' : ''}"
             data-id="${f.file_id}">
            <input type="checkbox" ${f.selected ? 'checked' : ''}>
            <span class="filename" title="${f.filename}">${f.filename}</span>
            <button class="delete-btn" title="Remove">&times;</button>
        </div>
    `).join('');

    // Add event listeners
    elements.fileList.querySelectorAll('.file-item').forEach(item => {
        const fileId = item.dataset.id;

        // Click filename to preview
        item.querySelector('.filename').addEventListener('click', () => {
            selectFile(fileId);
        });

        // Checkbox for selection
        item.querySelector('input[type="checkbox"]').addEventListener('change', (e) => {
            const file = state.files.find(f => f.file_id === fileId);
            if (file) file.selected = e.target.checked;
            updateUI();
        });

        // Delete button
        item.querySelector('.delete-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            await deleteFile(fileId);
        });
    });
}

// Delete file
async function deleteFile(fileId) {
    try {
        await fetch(`/files/${fileId}`, { method: 'DELETE' });
        state.files = state.files.filter(f => f.file_id !== fileId);

        if (state.activeFileId === fileId) {
            state.activeFileId = state.files.length > 0 ? state.files[0].file_id : null;
            state.beforeImageUrl = null;
            if (state.activeFileId) {
                updatePreview();
            } else {
                elements.previewImage.style.display = 'none';
                elements.comparisonContainer.style.display = 'none';
                elements.previewPlaceholder.style.display = 'block';
            }
        }

        updateUI();
    } catch (err) {
        console.error('Delete failed:', err);
    }
}

// Update all UI elements
function updateUI() {
    updateFileList();
    elements.fileCount.textContent = state.files.length;

    const selectedCount = state.files.filter(f => f.selected).length;
    elements.btnExportSelected.disabled = selectedCount === 0;
    elements.btnExportAll.disabled = state.files.length === 0;

    elements.btnSelectAll.textContent =
        state.files.length > 0 && state.files.every(f => f.selected)
            ? 'Deselect All'
            : 'Select All';
}

// Start the app
init();
