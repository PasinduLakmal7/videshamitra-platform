export const isValidPhoneNumber = (phone: string) => /^\+?[0-9]{9,15}$/.test(phone);
