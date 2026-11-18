import React, { createContext, useContext, useState } from 'react';

const AdminAuthContext = createContext<any>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [adminUser, setAdminUser] = useState(null);
  return <AdminAuthContext.Provider value={{ adminUser, setAdminUser }}>{children}</AdminAuthContext.Provider>;
};

export const useAdminAuth = () => useContext(AdminAuthContext);
