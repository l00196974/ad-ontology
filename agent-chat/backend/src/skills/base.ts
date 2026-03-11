import { SkillDefinition } from '../types';

export abstract class BaseSkill {
  abstract name: string;
  abstract description: string;
  abstract input_schema: SkillDefinition['input_schema'];

  abstract execute(args: Record<string, any>): Promise<any>;

  getDefinition(): SkillDefinition {
    return {
      name: this.name,
      description: this.description,
      input_schema: this.input_schema,
    };
  }
}
