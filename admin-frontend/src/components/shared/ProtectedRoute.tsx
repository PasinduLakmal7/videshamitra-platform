import React from 'react';

export const ProtectedRoute: React.FC<any> = (props) => {
  return <div className="protectedroute">{props.children}</div>;
};
