import React from 'react';

export const Spinner: React.FC<any> = (props) => {
  return <div className="spinner">{props.children}</div>;
};
