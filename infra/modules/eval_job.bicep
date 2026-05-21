// ACA Job for continuous (scheduled) evaluation of the routing-planner agent.
// Runs `python -m agent.evals.run_batch` on a cron schedule inside the same
// container image as the agent, reusing the existing managed environment and
// user-assigned identity. Writes results to stdout (captured in Log Analytics).

@description('Azure region.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Container Apps managed environment resource ID (reused from the agent app).')
param environmentId string

@description('Job name.')
param jobName string

@description('Resource ID of the user-assigned managed identity bound to the job.')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity.')
param userAssignedIdentityClientId string

@description('ACR login server for image pull via UAMI.')
param acrLoginServer string

@description('Container image. azd may swap this on deploy; defaults to the agent image tag.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Public URL of the agent /chat endpoint to evaluate.')
param agentChatUrl string

@description('Foundry Azure OpenAI endpoint (https://<sub>.openai.azure.com/).')
param azureOpenAiEndpoint string

@description('Azure OpenAI deployment name used as the LLM judge.')
param azureOpenAiDeployment string

@description('Azure OpenAI API version used by the judge.')
param azureOpenAiApiVersion string = '2024-10-21'

@description('Application Insights connection string.')
param appInsightsConnectionString string

@description('Cron expression for the schedule trigger. Default: daily at 10:00 UTC.')
param cronExpression string = '0 10 * * *'

@description('Max retries per execution.')
param replicaRetryLimit int = 1

@description('Replica timeout in seconds (job run hard cap).')
param replicaTimeout int = 1800

@description('CPU cores.')
param cpu string = '1.0'

@description('Memory.')
param memory string = '2.0Gi'

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: replicaTimeout
      replicaRetryLimit: replicaRetryLimit
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: acrLoginServer
          identity: userAssignedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'eval'
          image: image
          command: ['python']
          args: ['-m', 'agent.evals.run_batch']
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'AZURE_CLIENT_ID',                       value: userAssignedIdentityClientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AGENT_URL',                             value: agentChatUrl }
            { name: 'AZURE_OPENAI_ENDPOINT',                 value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT',               value: azureOpenAiDeployment }
            { name: 'AZURE_OPENAI_API_VERSION',              value: azureOpenAiApiVersion }
          ]
        }
      ]
    }
  }
}

output jobName string = job.name
output jobId string = job.id
