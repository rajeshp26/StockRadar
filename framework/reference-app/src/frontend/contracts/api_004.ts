// GENERATED from api-004.openapi.yaml — do not edit by hand.

export interface RefreshRequest {
  refresh_token: string;
  device_id?: string;
}

export interface RefreshResponse {
  access_token: string;
  expires_in: number;
  token_type: "Bearer";
  refresh_token?: string;
}

export interface Error {
  code: string;
  message: string;
}

