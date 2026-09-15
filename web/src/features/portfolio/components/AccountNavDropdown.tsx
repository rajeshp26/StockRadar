'use client';

import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';

interface AccountNavDropdownProps {
    accounts: { account_id: number; account_name: string; account_type: string }[];
    selectedAccountId: number | null;
    onSelect: (accountId: number | null) => void;
}

export function AccountNavDropdown({ accounts, selectedAccountId, onSelect }: AccountNavDropdownProps) {
    const selectedAccount = accounts.find((a) => a.account_id === selectedAccountId);

    return (
        <Select
            value={selectedAccountId == null ? 'all' : String(selectedAccountId)}
            onValueChange={(value) => onSelect(value === 'all' ? null : Number(value))}
        >
            <SelectTrigger className="w-[240px] glass-button-secondary" aria-label="Select account">
                <SelectValue
                    placeholder={
                        selectedAccount
                            ? `${selectedAccount.account_name} (${selectedAccount.account_type})`
                            : 'All Accounts'
                    }
                />
            </SelectTrigger>
            <SelectContent>
                <SelectItem value="all">All Accounts</SelectItem>
                {accounts.map((account) => (
                    <SelectItem key={account.account_id} value={String(account.account_id)}>
                        {account.account_name} ({account.account_type})
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}