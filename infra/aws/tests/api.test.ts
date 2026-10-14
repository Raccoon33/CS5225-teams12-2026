import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { App, RemovalPolicy, Stack } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { Api } from '../src/api.js';

for (const [stage, rate, burst] of [
  ['dev', 20, 40],
  ['prod', 20, 40],
  ['eval', 100, 200],
] as const) {
  test(`${stage} has the intended admission limit`, () => {
    const outdir = mkdtempSync(join(tmpdir(), 'flatsplit-api-test-'));
    try {
      const stack = new Stack(new App({ outdir }), `Test-${stage}`);
      new Api(stack, 'Api', { stage, removalPolicy: RemovalPolicy.DESTROY });
      const template = Template.fromStack(stack);
      template.resourceCountIs('AWS::ApiGatewayV2::Stage', 1);
      template.hasResourceProperties('AWS::ApiGatewayV2::Stage', {
        StageName: '$default',
        DefaultRouteSettings: {
          ThrottlingRateLimit: rate,
          ThrottlingBurstLimit: burst,
        },
      });
    } finally {
      rmSync(outdir, { recursive: true, force: true });
    }
  });
}
