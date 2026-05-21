@description('Azure region for the Foundry (Azure AI Services) account.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@minLength(2)
@maxLength(64)
@description('Azure AI Services (Foundry) account name.')
param accountName string

@description('Foundry project name (child of the account).')
param projectName string = 'routing-planner'

@description('Custom subdomain name (must be globally unique). Defaults to the account name.')
param customSubDomain string = accountName

@description('Model name to deploy.')
param modelName string = 'gpt-4.1'

@description('Model version.')
param modelVersion string = '2025-04-14'

@description('Model deployment name (used as the OpenAI deployment id).')
param deploymentName string = 'gpt-4.1'

@description('SKU name for the model deployment.')
param skuName string = 'GlobalStandard'

@description('SKU capacity (TPM x1000).')
param skuCapacity int = 50

@description('Object ID of the principal (UAMI) granted Cognitive Services OpenAI User.')
param appPrincipalId string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: customSubDomain
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: deploymentName
  sku: {
    name: skuName
    capacity: skuCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// Cognitive Services OpenAI User
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource appRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(appPrincipalId)) {
  scope: account
  name: guid(account.id, appPrincipalId, openAiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Azure AI User on the project (lets the UAMI read project + traces)
var aiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource appProjectRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(appPrincipalId)) {
  scope: project
  name: guid(project.id, appPrincipalId, aiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output accountName string = account.name
output accountId string = account.id
output endpoint string = account.properties.endpoint
output openAiEndpoint string = 'https://${customSubDomain}.openai.azure.com/'
output projectName string = project.name
output projectId string = project.id
output projectEndpoint string = 'https://${customSubDomain}.services.ai.azure.com/api/projects/${project.name}'
output deploymentName string = modelDeployment.name
