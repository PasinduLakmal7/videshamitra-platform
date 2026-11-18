import React from 'react';

export const RoleGuard: React.FC<any> = (props) => {
  return <div className="roleguard">{props.children}</div>;
};
