/**
 * Chart Utilities — Canvas-based chart rendering for DCF Model
 * 
 * No external dependencies. Uses the native Canvas 2D API.
 * All charts auto-handle devicePixelRatio for sharp rendering.
 */

class ChartUtils {

    // ─── Shared palette ───────────────────────────────────────────
    static COLORS = {
        cyan:       '#00d4ff',
        purple:     '#7c3aed',
        green:      '#10b981',
        amber:      '#f59e0b',
        red:        '#ef4444',
        blue:       '#3b82f6',
        indigo:     '#6366f1',
        pink:       '#ec4899',
        teal:       '#14b8a6',
        slate:      '#94a3b8',
        bg:         '#0f172a',
        cardBg:     '#1e293b',
        grid:       'rgba(148,163,184,0.12)',
        text:       '#e2e8f0',
        textMuted:  '#64748b',
    };

    static BAR_PALETTE = [
        '#00d4ff', '#3b82f6', '#6366f1', '#7c3aed',
        '#a855f7', '#ec4899', '#f43f5e', '#f59e0b',
        '#10b981', '#14b8a6',
    ];

    // ─── Setup canvas for HiDPI ───────────────────────────────────
    static setupCanvas(canvas) {
        const dpr    = window.devicePixelRatio || 1;
        const rect   = canvas.getBoundingClientRect();
        canvas.width  = rect.width  * dpr;
        canvas.height = rect.height * dpr;
        const ctx    = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        return { ctx, w: rect.width, h: rect.height };
    }

    // ═══════════════════════════════════════════════════════════════
    //  FCF Trend — Bar Chart
    // ═══════════════════════════════════════════════════════════════

    static drawFCFBarChart(canvas, years, fcfs) {
        const { ctx, w, h } = this.setupCanvas(canvas);
        const pad = { top: 40, right: 20, bottom: 45, left: 70 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top  - pad.bottom;

        // Clear
        ctx.clearRect(0, 0, w, h);

        // Title
        ctx.fillStyle = this.COLORS.text;
        ctx.font = '600 14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Free Cash Flow Projection', w / 2, 24);

        const maxVal = Math.max(...fcfs) * 1.15;
        const minVal = Math.min(0, Math.min(...fcfs));
        const range  = maxVal - minVal;

        const barCount = years.length;
        const barW     = Math.min(plotW / barCount * 0.6, 60);
        const gap      = (plotW - barW * barCount) / (barCount + 1);

        // Grid lines
        ctx.strokeStyle = this.COLORS.grid;
        ctx.lineWidth   = 1;
        const gridSteps = 5;
        for (let i = 0; i <= gridSteps; i++) {
            const y = pad.top + plotH * (1 - i / gridSteps);
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(pad.left + plotW, y);
            ctx.stroke();

            const val = minVal + range * (i / gridSteps);
            ctx.fillStyle = this.COLORS.textMuted;
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(this.formatCompact(val), pad.left - 8, y + 4);
        }

        // Bars
        for (let i = 0; i < barCount; i++) {
            const x = pad.left + gap + i * (barW + gap);
            const valRatio = (fcfs[i] - minVal) / range;
            const barH = valRatio * plotH;
            const y    = pad.top + plotH - barH;

            // Gradient fill
            const grad = ctx.createLinearGradient(x, y, x, y + barH);
            grad.addColorStop(0, this.COLORS.cyan);
            grad.addColorStop(1, this.COLORS.blue);
            ctx.fillStyle = grad;

            this.roundRect(ctx, x, y, barW, barH, 4);
            ctx.fill();

            // Value label
            ctx.fillStyle = this.COLORS.text;
            ctx.font = '600 10px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(this.formatCompact(fcfs[i]), x + barW / 2, y - 6);

            // Year label
            ctx.fillStyle = this.COLORS.textMuted;
            ctx.font = '11px Inter, sans-serif';
            ctx.fillText(`Y${years[i]}`, x + barW / 2, pad.top + plotH + 18);
        }

        // Y-axis label
        ctx.save();
        ctx.translate(14, h / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillStyle = this.COLORS.textMuted;
        ctx.font = '11px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('USD Millions', 0, 0);
        ctx.restore();
    }

    // ═══════════════════════════════════════════════════════════════
    //  Value Composition — Donut Chart
    // ═══════════════════════════════════════════════════════════════

    static drawDonutChart(canvas, pvFCFs, pvTV) {
        const { ctx, w, h } = this.setupCanvas(canvas);
        ctx.clearRect(0, 0, w, h);

        // Title
        ctx.fillStyle = this.COLORS.text;
        ctx.font = '600 14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Enterprise Value Composition', w / 2, 24);

        const total    = pvFCFs + pvTV;
        const cx       = w / 2;
        const cy       = h / 2 + 12;
        const radius   = Math.min(w, h) / 2 - 50;
        const innerR   = radius * 0.6;

        const slices = [
            { label: 'PV of FCFs',           value: pvFCFs, color: this.COLORS.cyan },
            { label: 'PV of Terminal Value',  value: pvTV,   color: this.COLORS.purple },
        ];

        let startAngle = -Math.PI / 2;

        slices.forEach((slice, i) => {
            const angle = (slice.value / total) * Math.PI * 2;
            const endAngle = startAngle + angle;

            ctx.beginPath();
            ctx.arc(cx, cy, radius, startAngle, endAngle);
            ctx.arc(cx, cy, innerR, endAngle, startAngle, true);
            ctx.closePath();
            ctx.fillStyle = slice.color;
            ctx.fill();

            // Label
            const midAngle = startAngle + angle / 2;
            const labelR   = radius + 22;
            const lx       = cx + Math.cos(midAngle) * labelR;
            const ly       = cy + Math.sin(midAngle) * labelR;
            const pct      = ((slice.value / total) * 100).toFixed(1);

            ctx.fillStyle = this.COLORS.text;
            ctx.font = '600 11px Inter, sans-serif';
            ctx.textAlign = midAngle > Math.PI / 2 && midAngle < Math.PI * 1.5 ? 'right' : 'left';
            ctx.fillText(`${slice.label}`, lx, ly - 6);
            ctx.fillStyle = slice.color;
            ctx.font = '700 13px Inter, sans-serif';
            ctx.fillText(`${pct}%`, lx, ly + 10);

            startAngle = endAngle;
        });

        // Center label
        ctx.fillStyle = this.COLORS.text;
        ctx.font = '700 16px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('EV', cx, cy - 4);
        ctx.fillStyle = this.COLORS.cyan;
        ctx.font = '600 12px Inter, sans-serif';
        ctx.fillText(`$${this.formatCompact(total)}M`, cx, cy + 14);
    }

    // ═══════════════════════════════════════════════════════════════
    //  Multi-line chart: Revenue / EBIT / FCF
    // ═══════════════════════════════════════════════════════════════

    static drawMultiLineChart(canvas, years, datasets) {
        const { ctx, w, h } = this.setupCanvas(canvas);
        const pad = { top: 40, right: 130, bottom: 45, left: 70 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top  - pad.bottom;

        ctx.clearRect(0, 0, w, h);

        // Title
        ctx.fillStyle = this.COLORS.text;
        ctx.font = '600 14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Key Metrics Trend', (w - pad.right + pad.left) / 2, 24);

        // Find global min/max
        let allVals = [];
        datasets.forEach(ds => allVals.push(...ds.data));
        const maxVal = Math.max(...allVals) * 1.1;
        const minVal = Math.min(0, Math.min(...allVals)) * 0.9;
        const range  = maxVal - minVal || 1;

        // Grid
        ctx.strokeStyle = this.COLORS.grid;
        ctx.lineWidth   = 1;
        for (let i = 0; i <= 5; i++) {
            const y = pad.top + plotH * (1 - i / 5);
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(pad.left + plotW, y);
            ctx.stroke();

            const val = minVal + range * (i / 5);
            ctx.fillStyle = this.COLORS.textMuted;
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(this.formatCompact(val), pad.left - 8, y + 4);
        }

        // X labels
        years.forEach((yr, i) => {
            const x = pad.left + (i / (years.length - 1 || 1)) * plotW;
            ctx.fillStyle = this.COLORS.textMuted;
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(`Y${yr}`, x, pad.top + plotH + 18);
        });

        // Lines
        datasets.forEach((ds, di) => {
            ctx.strokeStyle = ds.color;
            ctx.lineWidth   = 2.5;
            ctx.lineJoin    = 'round';
            ctx.beginPath();

            ds.data.forEach((val, i) => {
                const x = pad.left + (i / (years.length - 1 || 1)) * plotW;
                const y = pad.top + plotH * (1 - (val - minVal) / range);
                if (i === 0) ctx.moveTo(x, y);
                else         ctx.lineTo(x, y);
            });
            ctx.stroke();

            // Points
            ds.data.forEach((val, i) => {
                const x = pad.left + (i / (years.length - 1 || 1)) * plotW;
                const y = pad.top + plotH * (1 - (val - minVal) / range);
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, Math.PI * 2);
                ctx.fillStyle = ds.color;
                ctx.fill();
                ctx.strokeStyle = this.COLORS.bg;
                ctx.lineWidth = 2;
                ctx.stroke();
            });

            // Legend
            const ly = pad.top + 10 + di * 22;
            const lx = w - pad.right + 15;
            ctx.fillStyle = ds.color;
            ctx.fillRect(lx, ly - 5, 12, 12);
            ctx.fillStyle = this.COLORS.text;
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(ds.label, lx + 18, ly + 5);
        });

        // Y-axis label
        ctx.save();
        ctx.translate(14, h / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillStyle = this.COLORS.textMuted;
        ctx.font = '11px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('USD Millions', 0, 0);
        ctx.restore();
    }

    // ═══════════════════════════════════════════════════════════════
    //  Helpers
    // ═══════════════════════════════════════════════════════════════

    static roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    static formatCompact(n) {
        if (n == null || isNaN(n)) return '—';
        if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'T';
        if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'B';
        return n.toFixed(1);
    }
}
