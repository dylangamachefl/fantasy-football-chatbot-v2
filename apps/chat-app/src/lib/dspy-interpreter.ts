export interface DSPyPredictor {
    instructions: string;
    demos: any[];
    signature?: {
        instructions?: string;
        [key: string]: any;
    };
}

export interface CompiledProgram {
    predictors: DSPyPredictor[];
    [key: string]: any;
}

export class DSPyInterpreter {
    /**
     * Renders a full prompt from a compiled DSPy predictor.
     */
    static render(predictor: any, context: { [key: string]: string }): string {
        // Handle different possible nesting formats from DSPy exports
        const p = predictor.predictor || predictor['prog.predict'] || predictor;

        const instructions = p.signature?.instructions || p.instructions || "Your instructions here.";
        const demos = p.demos || [];

        let prompt = `${instructions}\n\n`;

        if (demos.length > 0) {
            prompt += "FEW-SHOT EXAMPLES:\n";
            demos.forEach((demo: any, i: number) => {
                prompt += `--- Example ${i + 1} ---\n`;
                Object.keys(demo).forEach(key => {
                    if (key !== 'embedding' && key !== 'score') {
                        prompt += `${key.toUpperCase()}: ${demo[key]}\n`;
                    }
                });
                prompt += `\n`;
            });
        }

        // Add dynamic context fields
        Object.keys(context).forEach(key => {
            prompt += `${key.toUpperCase()}: ${context[key]}\n`;
        });

        return prompt;
    }

    /**
     * Formats few-shot examples specifically for SQL tasks.
     */
    static formatSqlDemos(demos: any[]): string {
        return demos.map((d, i) => {
            return `Example ${i + 1}:\nQuestion: ${d.question}\nSQL: ${d.sql_query || d.sql}\n`;
        }).join('\n');
    }
}
