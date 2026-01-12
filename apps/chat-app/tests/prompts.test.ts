import { describe, it, expect, vi } from 'vitest';
import { PROMPTS } from '../src/lib/prompts';

describe('Prompts', () => {
  it('should generate a valid SQL generator prompt', () => {
    const prompt = PROMPTS.sqlGenerator(
      'Who is the best QB?',
      'CREATE TABLE QBs...',
      '',
      '',
      ''
    );
    expect(prompt).toContain('Who is the best QB?');
    expect(prompt).toContain('Generate a valid SQLite query');
    expect(prompt).toContain('Respond with ONLY the SQL query');
  });

  it('should include error context in SQL generator prompt when retrying', () => {
    const prompt = PROMPTS.sqlGenerator(
      'Who is the best QB?',
      'schema',
      'SELECT * FROM wrong',
      'Syntax Error',
      ''
    );
    expect(prompt).toContain('Previous Failed SQL: SELECT * FROM wrong');
    expect(prompt).toContain('Error Message: Syntax Error');
  });

  it('should generate a valid responder prompt', () => {
    const prompt = PROMPTS.responder('[]', '[{"name":"Tom"}]');
    expect(prompt).toContain('Answer the user\'s question based on the database results');
    expect(prompt).toContain('[{"name":"Tom"}]');
  });
});
