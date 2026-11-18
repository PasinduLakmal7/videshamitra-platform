import React from 'react';

export const Badge: React.FC<any> = (props) => {
  return <div className="badge">{props.children}</div>;
};
