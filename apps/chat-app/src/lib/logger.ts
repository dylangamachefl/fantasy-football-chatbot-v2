export interface LogEvent {
    id: string;
    timestamp: string;
    type: 'query' | 'feedback';

    // Query data
    userQuery?: string;
    workingMemory?: any;
    sqlGenerated?: string;
    dataRows?: number;
    answer?: string;

    // Performance & Debugging
    durationMs?: number;
    thoughtProcess?: string[];   // Agent reasoning steps
    tablesUsed?: string[];       // For understanding query complexity

    // Feedback (links to query by ID)
    queryId?: string;
    feedbackValue?: number;      // 1 or -1
    feedbackComment?: string;

    // For teacher-student
    category?: string;           // Query category for analysis
    promptVersion?: string;  // Track which prompt artifact was used
}

class Logger {
    private static readonly STORAGE_KEY = 'ff-agent-logs';
    private static readonly MAX_LOGS = 100;

    static logQuery(data: {
        userQuery: string;
        workingMemory: any;
        sqlGenerated: string;
        dataRows: number;
        answer: string;
        durationMs?: number;
        thoughtProcess?: string[];
        tablesUsed?: string[];
        category?: string;
        promptVersion?: string;
    }): string {
        const event: LogEvent = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            type: 'query',
            ...data,
            promptVersion: data.promptVersion || ((window as any).compiledPrograms ? 'optimized' : 'base')
        };

        this.addEvent(event);
        return event.id;
    }

    static logFeedback(queryId: string, value: number, comment?: string): void {
        const event: LogEvent = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            type: 'feedback',
            queryId,
            feedbackValue: value,
            feedbackComment: comment
        };

        this.addEvent(event);
    }

    private static addEvent(event: LogEvent): void {
        const logs = this.getAllLogs();
        logs.push(event);

        // Keep only last MAX_LOGS events
        if (logs.length > this.MAX_LOGS) {
            logs.shift();
        }

        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(logs));
    }

    static getAllLogs(): LogEvent[] {
        try {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            return stored ? JSON.parse(stored) : [];
        } catch (e) {
            console.error('[Logger] Failed to parse logs:', e);
            return [];
        }
    }

    // Helper method to get logs by feedback value
    private static getByFeedback(positive: boolean): LogEvent[] {
        const allLogs = this.getAllLogs();
        return allLogs.filter(e => e.type === 'feedback' && (positive ? e.feedbackValue! > 0 : e.feedbackValue! < 0))
            .map(feedback => {
                const query = allLogs.find(q => q.id === feedback.queryId && q.type === 'query');
                return query ? { ...query, feedbackValue: feedback.feedbackValue, feedbackComment: feedback.feedbackComment } : null;
            })
            .filter(Boolean) as LogEvent[];
    }

    // Get queries with negative feedback (failures - need Teacher labeling)
    static getFailures(): LogEvent[] {
        return this.getByFeedback(false);
    }

    // Get queries with positive feedback (successes - already golden!)
    static getSuccesses(): LogEvent[] {
        return this.getByFeedback(true);
    }

    // Export failures for Teacher model to label
    static exportFailuresForTeacher(): void {
        const failures = this.getFailures().map(f => ({
            question: f.userQuery,
            timestamp: f.timestamp,
            sql_attempted: f.sqlGenerated,
            working_memory: f.workingMemory,
            tables_used: f.tablesUsed,
            thought_process: f.thoughtProcess,
            feedback_value: -1,
            feedback_comment: f.feedbackComment || ''
        }));

        this.downloadJSON(failures, `failures-for-teacher-${new Date().toISOString()}.json`);
        console.log(`[Logger] Exported ${failures.length} failures for Teacher model`);
    }

    // Export successes as golden examples (already correct!)
    static exportSuccessesAsGolden(): void {
        const successes = this.getSuccesses().map(s => ({
            question: s.userQuery,
            sql: s.sqlGenerated,
            category: s.category || 'user-validated',
            answer: s.answer,
            reasoning: s.thoughtProcess?.join(' → ') || '',
            tables_used: s.tablesUsed || [],
            timestamp: s.timestamp,
            feedback_comment: s.feedbackComment || 'User approved'
        }));

        this.downloadJSON(successes, `successes-golden-${new Date().toISOString()}.json`);
        console.log(`[Logger] Exported ${successes.length} validated successes as golden examples`);
    }

    // Export all feedback data (both failures and successes)
    static exportAllWithFeedback(): void {
        const stats = this.getStats();
        const data = {
            metadata: {
                exported_at: new Date().toISOString(),
                total_queries: stats.totalQueries,
                total_feedback: stats.totalFeedback,
                failures_count: stats.totalFailures,
                successes_count: this.getSuccesses().length,
                positive_rate: stats.positiveRate
            },
            failures: this.getFailures().map(f => ({
                question: f.userQuery,
                sql_attempted: f.sqlGenerated,
                working_memory: f.workingMemory,
                tables_used: f.tablesUsed,
                thought_process: f.thoughtProcess,
                feedback_comment: f.feedbackComment,
                timestamp: f.timestamp
            })),
            successes: this.getSuccesses().map(s => ({
                question: s.userQuery,
                sql: s.sqlGenerated,
                answer: s.answer,
                reasoning: s.thoughtProcess?.join(' → '),
                tables_used: s.tablesUsed,
                feedback_comment: s.feedbackComment,
                timestamp: s.timestamp
            }))
        };

        this.downloadJSON(data, `all-feedback-${new Date().toISOString()}.json`);
        console.log(`[Logger] Exported all feedback: ${data.failures.length} failures, ${data.successes.length} successes`);
    }

    static exportLogs(): void {
        this.downloadJSON(this.getAllLogs(), `ff-agent-logs-${new Date().toISOString()}.json`);
    }

    static exportCurrentTrace(thoughts: string[]): void {
        const data = {
            timestamp: new Date().toISOString(),
            trace: thoughts,
            metadata: {
                userAgent: navigator.userAgent,
                version: '2.0.0-live-logic'
            }
        };
        this.downloadJSON(data, `agent-trace-${new Date().toISOString()}.json`);
    }

    static clearLogs(): void {
        localStorage.removeItem(this.STORAGE_KEY);
    }

    static getStats() {
        const logs = this.getAllLogs();
        const queries = logs.filter(l => l.type === 'query');
        const feedback = logs.filter(l => l.type === 'feedback');
        const failures = this.getFailures();

        return {
            totalQueries: queries.length,
            totalFeedback: feedback.length,
            totalFailures: failures.length,
            avgDuration: queries.reduce((sum, q) => sum + (q.durationMs || 0), 0) / queries.length || 0,
            positiveRate: feedback.filter(f => f.feedbackValue === 1).length / feedback.length || 0
        };
    }

    private static downloadJSON(data: any, filename: string): void {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
}

export default Logger;
