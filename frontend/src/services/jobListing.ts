import api from './api'

export interface JobListing {
  id: number
  job_title: string
  company_name: string
  salary_range?: string
  salary_avg?: number
  location?: string
  openings?: number
  requirements?: string
  search_keyword?: string
  data_year?: number
  created_at: string
}

export interface JobListingListResponse {
  items: JobListing[]
  total: number
  skip: number
  limit: number
  page: number
  pages: number
}

export interface JobListingQuery {
  skip?: number
  limit?: number
  job_title?: string
  company_name?: string
  location?: string
  search_keyword?: string
  data_year?: number
}

export interface SalaryStatistics {
  years: number[]
  categories: string[]
  data: Record<number, Record<string, number>>
}

export interface LocationStatistics {
  years: number[]
  provinces: string[]
  data: Record<number, Record<string, number>>
}

export interface WordCloudItem {
  name: string
  value: number
}

export interface WordCloudStatistics {
  years: number[]
  wordcloud: WordCloudItem[]
  year_statistics: Record<number, Record<string, number>>
  total_words: number
  unique_words: number
}

export const jobListingService = {
  // 获取招聘信息列表
  async getJobListings(params: JobListingQuery = {}): Promise<JobListingListResponse> {
    return api.get('/job-listings/', { params })
  },

  // 获取单个招聘信息
  async getJobListing(id: number): Promise<JobListing> {
    return api.get(`/job-listings/${id}`)
  },

  // 获取薪资统计数据
  async getSalaryStatistics(startYear: number = 2022, endYear: number = 2025): Promise<SalaryStatistics> {
    return api.get('/job-listings/salary-statistics', {
      params: { start_year: startYear, end_year: endYear }
    })
  },

  // 获取地理分布统计数据
  async getLocationStatistics(startYear: number = 2022, endYear: number = 2025): Promise<LocationStatistics> {
    return api.get('/job-listings/location-statistics', {
      params: { start_year: startYear, end_year: endYear }
    })
  },

  // 获取词云统计数据
  async getWordCloudStatistics(
    startYear: number = 2022, 
    endYear: number = 2025,
    topN: number = 100,
    minLength: number = 2
  ): Promise<WordCloudStatistics> {
    return api.get('/job-listings/wordcloud-statistics', {
      params: { 
        start_year: startYear, 
        end_year: endYear,
        top_n: topN,
        min_length: minLength
      }
    })
  },
}

