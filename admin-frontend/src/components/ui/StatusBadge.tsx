import React from 'react';

export const StatusBadge: React.FC<any> = (props) => {
  return <div className="statusbadge">{props.children}</div>;
};
