
'use client';

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, Settings, User } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/providers/auth-provider";

/**
 * Generates user initials from displayName or email.
 * Returns 1-2 uppercase characters for avatar fallback.
 *
 * @example
 * getInitials("Rajesh P", "rajesh@example.com") // "RP"
 * getInitials("Rajesh", "rajesh@example.com") // "RA"
 * getInitials(null, "rajesh@example.com") // "R"
 * getInitials(null, null) // "U"
 */
const getInitials = (
  name: string | null | undefined,
  email: string | null | undefined
): string => {
  // Try displayName first
  if (name && name.trim()) {
    const parts = name.trim().split(/\s+/).filter(Boolean);

    // Two or more words: use first letter of first two words
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }

    // Single word: use first two letters
    if (parts[0].length >= 2) {
      return parts[0].substring(0, 2).toUpperCase();
    }

    // Single character: return it
    if (parts[0].length === 1) {
      return parts[0].toUpperCase();
    }
  }

  // Fallback to email
  if (email && email.trim()) {
    return email.trim()[0].toUpperCase();
  }

  // Final fallback
  return 'U';
};

/**
 * UserNav Component
 *
 * Displays the authenticated user's avatar and a dropdown menu
 * with navigation links (Profile, Settings) and logout action.
 */
export function UserNav() {
  const { user, signOut } = useAuth();

  // Don't render if user is not authenticated
  if (!user) {
    return null;
  }

  const initials = getInitials(user.displayName, user.email);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="relative h-8 w-8 rounded-full p-0"
          aria-label={`Open user menu for ${user.displayName ?? 'User'}`}
        >
          <Avatar className="h-8 w-8">
            <AvatarImage
              src={user.photoURL ?? ""}
              alt={`${user.displayName ?? 'User'} profile picture`}
            />
            <AvatarFallback>{initials}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="w-56" align="end" forceMount>
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">
              {user.displayName ?? 'User'}
            </p>
            <p className="text-xs leading-none text-muted-foreground">
              {user.email}
            </p>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuGroup>
          {/* Navigation items: use asChild to render Link as the menu item */}
          <DropdownMenuItem asChild>
            <Link href="/profile">
              <User className="mr-2 h-4 w-4" />
              <span>Profile</span>
            </Link>
          </DropdownMenuItem>

          <DropdownMenuItem asChild>
            <Link href="/settings">
              <Settings className="mr-2 h-4 w-4" />
              <span>Settings</span>
            </Link>
          </DropdownMenuItem>
        </DropdownMenuGroup>

        <DropdownMenuSeparator />

        {/* Action item: use onSelect for logout */}
        <DropdownMenuItem onSelect={signOut}>
          <LogOut className="mr-2 h-4 w-4" />
          <span>Log out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
