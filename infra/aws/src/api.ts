import { Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import { HttpApi, HttpStage } from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { Architecture, Function, Runtime } from 'aws-cdk-lib/aws-lambda';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { pythonApiCode } from './python-code.js';

export interface ApiProps {
  readonly stage: string;
  readonly removalPolicy: RemovalPolicy;
}

/** HTTP API whose $default route invokes the Powertools resolver Lambda. */
export class Api extends Construct {
  readonly httpApi: HttpApi;
  /** Hostname CloudFront uses as the /api/* origin. */
  readonly originDomain: string;

  constructor(scope: Construct, id: string, props: ApiProps) {
    super(scope, id);

    const handler = new Function(this, 'HttpHandler', {
      runtime: Runtime.PYTHON_3_13,
      architecture: Architecture.ARM_64,
      code: pythonApiCode(),
      handler: 'flatsplit_api.handlers.http.handler',
      memorySize: 256,
      timeout: Duration.seconds(10),
      environment: {
        POWERTOOLS_SERVICE_NAME: 'flatsplit-api',
        POWERTOOLS_LOG_LEVEL: 'INFO',
        STAGE: props.stage,
      },
      logGroup: new LogGroup(this, 'HttpHandlerLogs', {
        retention: RetentionDays.ONE_WEEK,
        removalPolicy: props.removalPolicy,
      }),
    });

    this.httpApi = new HttpApi(this, 'HttpApi', {
      description: `FlatSplit ${props.stage} API`,
      createDefaultStage: false,
      defaultIntegration: new HttpLambdaIntegration('Handler', handler),
    });

    // The isolated capacity experiment must admit its 50 req/s workload.
    // Shared application stages retain the prototype abuse/cost limit.
    new HttpStage(this, 'DefaultStage', {
      httpApi: this.httpApi,
      stageName: '$default',
      autoDeploy: true,
      throttle:
        props.stage === 'eval'
          ? { rateLimit: 100, burstLimit: 200 }
          : { rateLimit: 20, burstLimit: 40 },
    });

    const stack = Stack.of(this);
    this.originDomain = `${this.httpApi.apiId}.execute-api.${stack.region}.${stack.urlSuffix}`;
  }
}
