@description('Azure region.')
param location string

@description('Tags applied to the Key Vault.')
param tags object = {}

@minLength(3)
@maxLength(24)
@description('Key Vault name.')
param name string

@description('Object ID granted Key Vault Secrets Officer role (typically the deploying user). Empty to skip.')
param principalId string = ''

@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@description('Object ID of the application principal (typically a UAMI) granted Key Vault Secrets User (read-only). Empty to skip.')
param appPrincipalId string = ''

@secure()
@description('Optional MCP API key value. When non-empty, persisted as the "mcp-api-key" secret.')
param mcpApiKey string = ''

resource kv 'Microsoft.KeyVault/vaults@2024-04-01-preview' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// Key Vault Secrets Officer
var secretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: kv
  name: guid(kv.id, principalId, secretsOfficerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsOfficerRoleId)
    principalId: principalId
    principalType: principalType
  }
}

// Key Vault Secrets User (read secret values at runtime)
var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource appRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(appPrincipalId)) {
  scope: kv
  name: guid(kv.id, appPrincipalId, secretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource mcpApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2024-04-01-preview' = if (!empty(mcpApiKey)) {
  parent: kv
  name: 'mcp-api-key'
  properties: {
    value: mcpApiKey
    contentType: 'text/plain'
  }
}

output name string = kv.name
output uri string = kv.properties.vaultUri
output mcpApiKeySecretUri string = empty(mcpApiKey) ? '' : mcpApiKeySecret.properties.secretUri
