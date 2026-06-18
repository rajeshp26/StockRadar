export interface User {
  user_id: number;
  auth_id: string;
  email: string;
  username: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  preferred_currency: string;
  last_signed_in: string;
}

export function getUserDisplayName(user: User): string {
  if (user.first_name && user.last_name) {
    return `${user.first_name} ${user.last_name}`;
  }
  if (user.first_name) {
    return user.first_name;
  }
  if (user.username && user.username !== user.email) {
    return user.username;
  }
  return user.email;
}

export function getUserInitials(user: User): string {
  if (user.first_name && user.last_name) {
    return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
  }
  if (user.first_name) {
    return user.first_name[0].toUpperCase();
  }
  return user.email[0].toUpperCase();
}