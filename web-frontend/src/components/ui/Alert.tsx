import React from 'react';

export const Alert: React.FC<any> = (props) => {
  return <div className="alert">{props.children}</div>;
};
