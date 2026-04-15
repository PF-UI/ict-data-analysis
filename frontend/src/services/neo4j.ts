import api from './api'

export interface Neo4jNode {
  id: number
  labels: string[]
  properties: Record<string, any>
}

export interface Neo4jRelationship {
  source: Neo4jNode
  relationship: {
    type: string
    properties: Record<string, any>
  }
  target: Neo4jNode
}

export interface QueryRequest {
  query: string
  parameters?: Record<string, any>
}

export interface SearchRequest {
  label?: string
  property_key?: string
  property_value?: string
  limit?: number
}

/** api 拦截器已解包为 response.data，此处显式标注返回类型 */
export interface Neo4jStats {
  nodes: Record<string, number>
  relationships: Record<string, number>
}

export interface QueryExecuteResult {
  results?: any[]
}

export interface NodesListResult {
  nodes?: Neo4jNode[]
}

export interface BrowserUrlResult {
  url: string
}

export const neo4jService = {
  async getStats(): Promise<Neo4jStats> {
    return api.get('/neo4j/stats') as Promise<Neo4jStats>
  },

  async executeQuery(request: QueryRequest): Promise<QueryExecuteResult> {
    return api.post('/neo4j/query', request) as Promise<QueryExecuteResult>
  },

  async searchNodes(request: SearchRequest): Promise<NodesListResult> {
    return api.post('/neo4j/search', request) as Promise<NodesListResult>
  },

  async getNodes(limit = 100): Promise<NodesListResult> {
    return api.get('/neo4j/nodes', { params: { limit } }) as Promise<NodesListResult>
  },

  async getNodeById(nodeId: number): Promise<any> {
    return api.get(`/neo4j/nodes/${nodeId}`)
  },

  async getRelationships(limit = 100) {
    return api.get('/neo4j/relationships', { params: { limit } })
  },

  async getBrowserUrl(): Promise<BrowserUrlResult> {
    return api.get('/neo4j/browser/url') as Promise<BrowserUrlResult>
  },
}
